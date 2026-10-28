#!/usr/bin/env node
// Research transport only: QEMU runs in Chromium; Node adapts QMP/UART/files.
import { createServer as createHttpServer } from 'node:http';
import { createServer as createSocketServer } from 'node:net';
import {
  readFile,
  writeFile,
  mkdir,
  stat,
  realpath,
  readdir,
  unlink
} from 'node:fs/promises';
import { resolve, dirname, basename, extname, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
const here = dirname(fileURLToPath(import.meta.url));
const moduleDirectory = process.env.M5_WASM_NODE_MODULES;
const { chromium } = moduleDirectory
  ? createRequire(pathToFileURL(resolve(moduleDirectory, '_resolver.cjs')))(
      'playwright'
    )
  : await import('playwright');
const runtimeDirectory = process.env.M5_WASM_RUNTIME_DIR;
if (!runtimeDirectory) {
  throw new Error(
    'M5_WASM_RUNTIME_DIR must point to the reviewed QEMU WASM build'
  );
}
const runtime = resolve(runtimeDirectory);
const clockProfile = process.env.M5_WASM_CLOCK_PROFILE || 'wallclock';
if (!['wallclock', 'icount-single', 'icount-fixed-8', 'vm-div8'].includes(clockProfile)) {
  throw new Error('Unsupported M5_WASM_CLOCK_PROFILE');
}
const argv = process.argv.slice(2),
  args = [],
  files = [],
  channels = [],
  environment = {},
  servers = [],
  sockets = new Set(),
  ownedSocketPaths = [];
const report = {
  schema_version: 1,
  backend: 'browser-qemu-wasm',
  firmware_execution: 'NOT RUN',
  started_at: new Date().toISOString(),
  runtime,
  original_arguments: argv,
  arguments: args,
  files: [],
  channels,
  environment_keys: [],
  workers_created: [],
  workers_closed: [],
  events: [],
  errors: [],
  cleanup: {}
};
let qmpPath,
  sessionRoot,
  page,
  browser,
  browserServer,
  httpServer,
  client,
  greeting,
  closing = false,
  exitCode,
  outputChain = Promise.resolve(),
  inputChain = Promise.resolve(),
  reportPath,
  receipt = {};
const pending = [];
let requestSequence = 0,
  capabilitiesNegotiated = false;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const log = (kind, data) =>
  report.events.push({ at: new Date().toISOString(), kind, data });
const inside = (root, path) =>
  relative(root, path) === '' ||
  (!relative(root, path).startsWith('..') &&
    !relative(root, path).startsWith('/'));
function owned(path) {
  const absolute = resolve(path);
  if (!inside(sessionRoot, absolute))
    throw new Error('Path outside owned session');
  return absolute;
}
async function preload(path) {
  const absolute = await realpath(path),
    info = await stat(absolute);
  if (!info.isFile() || info.size > 64 * 1024 * 1024)
    throw new Error('Preload must be a regular file <=64 MiB');
  if (files.some((item) => item.path === absolute)) return absolute;
  const bytes = await readFile(absolute);
  files.push({ path: absolute, bytes, url: '/files/' + files.length });
  report.files.push({
    path: absolute,
    bytes: bytes.length,
    sha256: hash(bytes)
  });
  return absolute;
}
async function preloadTree(path) {
  for (const entry of await readdir(path, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const child = resolve(path, entry.name);
    if (entry.isFile()) await preload(child);
    else if (entry.isDirectory()) await preloadTree(child);
  }
}
function channel(id, path, hostPath, duplex) {
  const item = { id, path, hostPath, duplex };
  Object.defineProperty(item, 'socket', {
    value: null,
    writable: true,
    enumerable: false
  });
  channels.push(item);
  return item;
}
async function socketServer(path, onConnect) {
  await mkdir(dirname(path), { recursive: true });
  try {
    await stat(path);
    throw new Error('Refusing to replace existing socket path');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const server = createSocketServer((socket) => {
    sockets.add(socket);
    // A local QMP/UART reader may close while an asynchronous browser reply
    // is being written. That transport failure belongs to this client, not
    // to the owned VM or Chromium process.
    socket.on('error', (error) => {
      log('client_socket_error', {
        endpoint: path,
        code: error.code || null,
        message: error.message
      });
      socket.destroy();
    });
    socket.on('close', () => sockets.delete(socket));
    onConnect(socket);
  });
  await new Promise((ok, bad) => {
    server.once('error', bad);
    server.listen(path, ok);
  });
  servers.push(server);
  ownedSocketPaths.push(path);
  return server;
}
async function push(name, bytes) {
  await page.evaluate(({ name, bytes }) => bridgePush(name, bytes), {
    name,
    bytes: [...bytes]
  });
}
function sendInput(bytes) {
  inputChain = inputChain.then(() => push('qmp', bytes)).catch(fatal);
}
async function receiveRequest(line, recipient) {
  const original = JSON.parse(line);
  if (!original.execute) throw new Error('QMP request must contain execute');
  const message = structuredClone(original),
    bridgeId = 'browser-bridge-' + ++requestSequence;
  if (message.execute === 'screendump') {
    if (!message.arguments?.filename)
      throw new Error('screendump needs filename');
    message.arguments.filename = owned(message.arguments.filename);
    await page.evaluate(
      (path) => bridgeMkdir(path),
      dirname(message.arguments.filename)
    );
  }
  const reuseCapabilities =
    message.execute === 'qmp_capabilities' && capabilitiesNegotiated;
  if (reuseCapabilities) {
    if (
      Object.keys(message.arguments || {}).some((key) => key !== 'enable') ||
      (message.arguments?.enable || []).length
    )
      throw new Error(
        'Reconnect does not renegotiate optional QMP capabilities'
      );
    message.execute = 'query-status';
    delete message.arguments;
  }
  message.id = bridgeId;
  pending.push({ original, message, bridgeId, recipient, reuseCapabilities });
  await push('qmp', Buffer.from(JSON.stringify(message) + '\n'));
}
async function receiveOutput(line) {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    process.stdout.write(line + '\n');
    return;
  }
  if (message.QMP) {
    greeting = line + '\n';
    client?.write(greeting);
    log('qmp_greeting', message);
    return;
  }
  if (message.return !== undefined || message.error !== undefined) {
    const index = pending.findIndex((item) => item.bridgeId === message.id);
    const request = index >= 0 ? pending.splice(index, 1)[0] : null;
    if (request) {
      if (request.message.execute === 'screendump' && !message.error) {
        const bytes = Buffer.from(
          await page.evaluate(
            (path) => bridgeRead(path),
            request.message.arguments.filename
          ),
          'base64'
        );
        await writeFile(owned(request.message.arguments.filename), bytes);
        log('screendump_export', { bytes: bytes.length, sha256: hash(bytes) });
      }
      if (request.original.execute === 'qmp_capabilities' && !message.error) {
        if (request.reuseCapabilities) {
          if (typeof message.return?.status !== 'string')
            throw new Error('Existing QMP connection health not proven');
          log('reconnect_capabilities_reused', {
            actualQueryStatus: message.return
          });
          // The underlying stdio monitor stays negotiated; a new UNIX client
          // gets an ACK only after the original QEMU confirms its live state.
          message.return = {};
        } else capabilitiesNegotiated = true;
      }
      if (Object.hasOwn(request.original, 'id'))
        message.id = request.original.id;
      else delete message.id;
      if (!request.recipient.destroyed)
        request.recipient.write(JSON.stringify(message) + '\n');
      else
        log('qmp_response_discarded', {
          bridgeId: request.bridgeId,
          execute: request.original.execute,
          reason: 'recipient_closed'
        });
    } else client?.write(line + '\n');
  } else client?.write(line + '\n');
  log('qmp_response', message);
}
async function finish(code, reason) {
  if (closing) return;
  closing = true;
  clearTimeout(startupTimer);
  clearTimeout(lifetimeTimer);
  clearInterval(parentTimer);
  log('finish', reason);
  try {
    const deadline = Date.now() + 2000;
    while (
      exitCode !== undefined &&
      page?.workers().length &&
      Date.now() < deadline
    )
      await new Promise((done) => setTimeout(done, 25));
    report.cleanup.workers_before_browser_close =
      page?.workers().length ?? null;
    report.cleanup.natural_runtime_exit = exitCode !== undefined;
    report.cleanup.runtime_exit_code = exitCode ?? null;
    if (browserServer) {
      let closed = false;
      await Promise.race([
        browserServer.close().then(() => {
          closed = true;
        }),
        new Promise((resolve) => setTimeout(resolve, 1200))
      ]);
      if (!closed) {
        report.cleanup.browser_forced_kill = true;
        await browserServer.kill();
      }
      report.cleanup.browser_pid_gone =
        browserServer.process().exitCode !== null ||
        browserServer.process().signalCode !== null;
    } else if (browser) await browser.close();
    report.cleanup.browser_closed = true;
  } catch (error) {
    report.errors.push(String(error));
  }
  for (const socket of sockets) socket.destroy();
  for (const server of servers) await new Promise((done) => server.close(done));
  if (httpServer) await new Promise((done) => httpServer.close(done));
  for (const path of ownedSocketPaths) await unlink(path).catch(() => {});
  report.cleanup.sockets_removed = ownedSocketPaths;
  report.finished_at = new Date().toISOString();
  report.status = code === 0 ? 'PASS' : 'FAIL';
  if (reportPath)
    await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n').catch(
      () => {}
    );
  process.stdout.write(
    'BROWSER_QEMU_RECEIPT ' +
      JSON.stringify({
        ...receipt,
        phase: 'exit',
        exitCode: code,
        reason,
        actualWorker: {
          created: report.workers_created.length,
          closed: report.workers_closed.length,
          beforeBrowserClose: report.cleanup.workers_before_browser_close
        },
        cleanup: report.cleanup
      }) +
      '\n'
  );
  process.exitCode = code;
}
async function fatal(error) {
  report.errors.push(error.stack || String(error));
  process.stderr.write('BROWSER_WASM_ADAPTER ' + String(error) + '\n');
  if (!report.fatal_observation_started && !closing) {
    report.fatal_observation_started = true;
    try {
      report.fatal_observation = await Promise.race([
        page?.evaluate(
          () => globalThis.bridgeDiagnostics?.() ?? { bridgeUnavailable: true }
        ),
        new Promise((resolve) =>
          setTimeout(() => resolve({ timeout: true }), 1500)
        )
      ]);
      report.fatal_workers = page?.workers().length ?? null;
    } catch (observationError) {
      report.fatal_observation_error = String(observationError);
    }
  }
  await finish(1, 'error');
}
const startupTimer = setTimeout(
  () => fatal(new Error('Browser QMP startup timeout')),
  55000
);
const lifetimeTimer = setTimeout(
  () => fatal(new Error('Owned adapter lifetime exceeded')),
  Number(process.env.M5_WASM_MAX_LIFETIME_MS || 600000)
);
const parentPid = process.ppid,
  parentTimer = setInterval(() => {
    if (process.ppid !== parentPid)
      fatal(new Error('Owner process disappeared'));
  }, 1000);
async function stop(signal) {
  log('signal', signal);
  if (page && greeting) {
    sendInput(
      Buffer.from(
        JSON.stringify({ execute: 'quit', id: 'adapter-owned-shutdown' }) + '\n'
      )
    );
    setTimeout(
      () => finish(1, 'forced-browser-close-after-stop-timeout'),
      3000
    ).unref();
  } else await finish(1, 'cancel-before-qmp-ready');
}
process.on('SIGTERM', () => stop('SIGTERM'));
process.on('SIGINT', () => stop('SIGINT'));
try {
  const qmpIndex = argv.indexOf('-qmp');
  if (qmpIndex < 0 || !argv[qmpIndex + 1]?.startsWith('unix:'))
    throw new Error('Expected service-owned UNIX QMP');
  qmpPath = resolve(argv[qmpIndex + 1].slice(5).split(',')[0]);
  const driveIndex = argv.indexOf('-drive'),
    driveFile =
      driveIndex >= 0
        ? argv[driveIndex + 1]
            ?.split(',')
            .find((x) => x.startsWith('file='))
            ?.slice(5)
        : null;
  sessionRoot = resolve(
    process.env.M5_WASM_SESSION_ROOT ||
      (driveFile ? dirname(driveFile) : dirname(qmpPath))
  );
  if (sessionRoot === '/tmp' || sessionRoot === '/')
    throw new Error('Explicit session ownership root required');
  reportPath = resolve(sessionRoot, 'browser-wasm-adapter.json');
  await mkdir(sessionRoot, { recursive: true });
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (['-S', '-nodefaults', '-no-reboot'].includes(flag)) {
      args.push(flag);
      continue;
    }
    const value = argv[++i];
    if (value === undefined) throw new Error('Missing argument ' + flag);
    if (
      [
        '-M',
        '-machine',
        '-m',
        '-display',
        '-monitor',
        '-global',
        '-device',
        '-icount',
        '-rtc',
        '-accel',
        '-mon'
      ].includes(flag)
    ) {
      args.push(flag, value);
      continue;
    }
    if (flag === '-qmp') {
      args.push('-qmp', 'stdio');
      continue;
    }
    if (flag === '-L') {
      const directory = await realpath(value);
      await preloadTree(directory);
      args.push(flag, directory);
      continue;
    }
    if (flag === '-drive') {
      const parts = value.split(','),
        fileIndex = parts.findIndex((x) => x.startsWith('file='));
      if (fileIndex < 0) throw new Error('Drive needs explicit file');
      const path = owned(parts[fileIndex].slice(5));
      parts[fileIndex] = 'file=' + (await preload(path));
      args.push(flag, parts.join(','));
      report.firmware_execution = 'PENDING';
      continue;
    }
    if (flag === '-chardev') {
      const fields = Object.fromEntries(
        value
          .split(',')
          .slice(1)
          .map((x) => x.split('='))
      );
      if (
        !value.startsWith('socket,') ||
        fields.id !== 'program-console' ||
        !fields.path ||
        fields.server !== 'on'
      )
        throw new Error('Unsupported chardev transport');
      const hostPath = resolve(fields.path),
        path = '/bridge/console';
      if (
        !inside(sessionRoot, hostPath) &&
        hostPath !== qmpPath.replace('/m5-service-', '/m5-console-')
      )
        throw new Error('Console is not owned by this session');
      channel(fields.id, path, hostPath, true);
      args.push(flag, `pipe,id=${fields.id},path=${path}`);
      continue;
    }
    if (flag === '-serial') {
      if (
        value === 'none' ||
        value === 'null' ||
        value === 'chardev:program-console'
      ) {
        args.push(flag, value);
        continue;
      }
      if (!value.startsWith('file:'))
        throw new Error('Unsupported serial backend');
      const id = 'serial' + channels.length,
        path = '/bridge/' + id;
      channel(id, path, owned(value.slice(5)), false);
      args.push(flag, 'file:' + path);
      continue;
    }
    throw new Error('Unsupported native option ' + flag);
  }
  if (clockProfile.startsWith('icount-')) {
    if (args.includes('-accel') || args.includes('-icount')) {
      throw new Error('Clock profile conflicts with explicit accelerator/icount');
    }
    const shift = clockProfile === 'icount-fixed-8' ? '8' : 'auto';
    args.push('-accel', 'tcg,thread=single', '-icount', `shift=${shift},align=off,sleep=off`);
  }
  if (clockProfile === 'vm-div8') {
    if (args.includes('-icount')) throw new Error('VM clock divisor conflicts with icount');
    environment.M5_WASM_VM_CLOCK_DIVISOR = '8';
  }
  report.clock_profile = clockProfile;
  for (const [key, value] of Object.entries(process.env)) {
    if (/^M5SW_/.test(key)) environment[key] = value;
  }
  if (process.env.M5_UNIT_CONFIG) {
    environment.M5_UNIT_CONFIG = await preload(
      owned(process.env.M5_UNIT_CONFIG)
    );
  }
  report.environment_keys = Object.keys(environment);
  receipt = {
    clockProfile,
    engine: 'browser-wasm',
    originalArgvSha256: hash(Buffer.from(JSON.stringify(argv))),
    actualArgv: args,
    sessionRoot,
    qmpPath,
    environmentKeys: report.environment_keys,
    artifacts: {}
  };
  for (const name of [
    'qemu-system-xtensa.js',
    'qemu-system-xtensa.wasm',
    'qemu-system-xtensa.worker.js'
  ]) {
    const bytes = await readFile(resolve(runtime, name));
    receipt.artifacts[name] = { bytes: bytes.length, sha256: hash(bytes) };
  }
  if (process.env.M5_WASM_SOURCE_RECEIPT) {
    const bytes = await readFile(process.env.M5_WASM_SOURCE_RECEIPT);
    receipt.sourceReceipt = { sha256: hash(bytes), body: JSON.parse(bytes) };
  }
  for (const item of channels) {
    if (item.duplex)
      await socketServer(item.hostPath, (socket) => {
        item.socket = socket;
        socket.once('close', () => {
          if (item.socket === socket) item.socket = null;
        });
        socket.on('data', (bytes) => {
          inputChain = inputChain.then(() => push(item.id, bytes)).catch(fatal);
        });
      });
    else {
      await writeFile(item.hostPath, '');
    }
  }
  const types = {
    '.js': 'text/javascript',
    '.html': 'text/html',
    '.wasm': 'application/wasm'
  };
  httpServer = createHttpServer(async (request, response) => {
    try {
      const pathname = new URL(request.url, 'http://localhost').pathname;
      let bytes, type;
      if (pathname === '/config.json') {
        bytes = JSON.stringify({
          arguments: args,
          files: files.map(({ path, url }) => ({ path, url })),
          channels: channels.map(({ id, path, duplex }) => ({
            id,
            path,
            duplex
          })),
          environment
        });
        type = 'application/json';
      } else if (pathname.startsWith('/files/')) {
        bytes = files[Number(pathname.slice(7))]?.bytes;
        if (!bytes) throw new Error('Unknown file');
        type = 'application/octet-stream';
      } else if (pathname === '/') {
        bytes =
          '<!doctype html><meta charset="utf-8"><title>Research browser QEMU</title><script type="module" src="/browser.mjs"></script>';
        type = 'text/html';
      } else {
        const name = pathname.slice(1);
        if (
          ![
            'browser.mjs',
            'page.js',
            'qemu-system-xtensa.js',
            'qemu-system-xtensa.wasm',
            'qemu-system-xtensa.worker.js'
          ].includes(name)
        )
          throw new Error('Unknown resource');
        bytes = await readFile(
          resolve(name.startsWith('qemu-') ? runtime : here, name)
        );
        type = types[extname(name)] || 'text/javascript';
      }
      response
        .writeHead(200, {
          'Content-Type': type,
          'Cache-Control': 'no-store',
          'Cross-Origin-Opener-Policy': 'same-origin',
          'Cross-Origin-Embedder-Policy': 'require-corp'
        })
        .end(bytes);
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((done) => httpServer.listen(0, '127.0.0.1', done));
  const port = httpServer.address().port;
  if ([8787, 8830].includes(port))
    throw new Error('Reserved user service port');
  report.origin = 'http://127.0.0.1:' + port;
  process.stderr.write('BROWSER_WASM_LAUNCH_START\n');
  browserServer = await chromium.launchServer({
    headless: true,
    handleSIGTERM: false,
    handleSIGINT: false,
    handleSIGHUP: false,
    ...(process.env.M5_WASM_CHROME
      ? { executablePath: process.env.M5_WASM_CHROME }
      : {})
  });
  report.browser_pid = browserServer.process().pid;
  if (closing) {
    await browserServer.kill();
    report.cleanup.cancelled_startup_browser_pid_gone =
      browserServer.process().exitCode !== null ||
      browserServer.process().signalCode !== null;
    await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    throw new Error('Owned browser startup cancelled');
  }
  browser = await chromium.connect(browserServer.wsEndpoint());
  if (closing) {
    await browserServer.kill();
    throw new Error('Owned browser connection cancelled');
  }
  report.browser = browser.version();
  receipt.browser = report.browser;
  process.stdout.write(
    'BROWSER_QEMU_RECEIPT ' +
      JSON.stringify({ ...receipt, phase: 'start' }) +
      '\n'
  );
  page = await browser.newPage();
  page.on('worker', (worker) => {
    report.workers_created.push(worker.url());
    worker.on('close', () => report.workers_closed.push(worker.url()));
  });
  page.on('pageerror', fatal);
  await page.exposeFunction('hostBridge', (name, value) => {
    if (name === 'qmp') {
      outputChain = outputChain
        .then(() => receiveOutput(value.trimEnd()))
        .catch(fatal);
    } else if (name === 'stderr') process.stderr.write(value);
    else if (name === 'abort') fatal(new Error('WASM abort ' + value));
    else if (name === 'runtime') {
      report.runtime_state = value;
      log('runtime', value);
    } else if (name === 'exit') {
      exitCode = value;
      log('runtime_exit', value);
      setTimeout(() => finish(value, 'runtime-exit'), 250);
    } else {
      const item = channels.find((x) => x.id === name);
      if (!item) throw new Error('Unknown output channel');
      const bytes = Buffer.from(value);
      if (item.duplex) item.socket?.write(bytes);
      else
        outputChain = outputChain
          .then(() =>
            import('node:fs/promises').then((fs) =>
              fs.appendFile(item.hostPath, bytes)
            )
          )
          .catch(fatal);
    }
  });
  await page.goto(report.origin + '/');
  await page.waitForFunction(() => globalThis.bridgeReady, undefined, {
    timeout: 50000
  });
  while (!greeting) await new Promise((done) => setTimeout(done, 10));
  clearTimeout(startupTimer);
  await socketServer(qmpPath, (socket) => {
    if (client && !client.destroyed)
      log('qmp_client_overlap', { requestsInFlight: pending.length });
    client = socket;
    client.once('close', () => {
      if (client === socket) client = null;
      log('qmp_client_closed', {
        pending: pending.filter((item) => item.recipient === socket).length
      });
    });
    client.write(greeting);
    let buffer = '';
    socket.on('data', (bytes) => {
      buffer += bytes.toString();
      if (buffer.length > 1024 * 1024) {
        socket.destroy();
        return;
      }
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 1);
        if (line.trim())
          inputChain = inputChain
            .then(() => receiveRequest(line, socket))
            .catch(fatal);
      }
    });
  });
  log('transport_ready', { qmp_path: qmpPath });
  process.stderr.write('BROWSER_WASM_TRANSPORT_READY\n');
} catch (error) {
  await fatal(error);
}
