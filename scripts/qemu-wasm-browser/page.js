export async function createQemuPage() {
  const config = await (await fetch('./config.json')).json();
  const { default: createQemu } = await import('./qemu-system-xtensa.js');
  const queues = new Map([['qmp', []]]);
  let module;
  globalThis.bridgePush = (name, bytes) => {
    const queue = queues.get(name);
    if (!queue) throw new Error('Unknown bridge input: ' + name);
    queue.push(...bytes);
  };
  globalThis.bridgeRead = (path) => {
    const bytes = module.FS.readFile(path),
      chunks = [];
    for (let i = 0; i < bytes.length; i += 32768)
      chunks.push(String.fromCharCode(...bytes.subarray(i, i + 32768)));
    const result = btoa(chunks.join(''));
    module.FS.unlink(path);
    return result;
  };
  globalThis.bridgeMkdir = (path) => module.FS.mkdirTree(path);
  globalThis.bridgeDiagnostics = () => ({
    at: new Date().toISOString(),
    crossOriginIsolated,
    // This is the main thread's current view, not a claim about another thread's heap.
    mainThreadHeapViewBytes: module?.HEAPU8?.buffer?.byteLength ?? null,
    shared: module?.HEAPU8?.buffer instanceof SharedArrayBuffer,
    queuedInputBytes: Object.fromEntries(
      [...queues].map(([name, bytes]) => [name, bytes.length])
    )
  });
  const preloads = await Promise.all(
    config.files.map(async (item) => ({
      ...item,
      bytes: new Uint8Array(await (await fetch(item.url)).arrayBuffer())
    }))
  );
  const options = {
    arguments: config.arguments,
    locateFile: (name) => new URL(name, location.href).href,
    mainScriptUrlOrBlob: new URL('./qemu-system-xtensa.js', location.href).href,
    print: (text) => hostBridge('qmp', String(text) + '\n'),
    printErr: (text) => hostBridge('stderr', String(text) + '\n'),
    onAbort: (error) => hostBridge('abort', String(error)),
    onExit: (code) => hostBridge('exit', code),
    stdin: () => queues.get('qmp').shift(),
    preRun: [
      (m) => {
        module = m;
        for (const item of preloads) {
          m.FS.mkdirTree(item.path.slice(0, item.path.lastIndexOf('/')) || '/');
          m.FS.writeFile(item.path, item.bytes);
        }
        if (Object.keys(config.environment).length) {
          if (!m.ENV)
            throw new Error(
              'Runtime must export ENV for real board environment'
            );
          Object.assign(m.ENV, config.environment);
        }
        m.FS.mkdirTree('/bridge');
        config.channels.forEach((channel, index) => {
          const input = [];
          queues.set(channel.id, input);
          const create = (path, readable) => {
            const dev = m.FS.makedev(64, index * 2 + (readable ? 0 : 1));
            m.FS.registerDevice(dev, {
              open: (stream) => {
                stream.seekable = false;
              },
              close: () => {},
              read: (stream, buffer, offset, length) => {
                if (!input.length) throw new m.FS.ErrnoError(6);
                const n = Math.min(input.length, length);
                for (let i = 0; i < n; i++) buffer[offset + i] = input.shift();
                return n;
              },
              write: (stream, buffer, offset, length) => {
                hostBridge(
                  channel.id,
                  Array.from(buffer.subarray(offset, offset + length))
                );
                return length;
              },
              poll: () => 4 | (input.length ? 1 : 0),
              llseek: () => {
                throw new m.FS.ErrnoError(70);
              }
            });
            m.FS.mkdev(path, 0o666, dev);
          };
          if (channel.duplex) {
            create(channel.path + '.in', true);
            create(channel.path + '.out', false);
          } else create(channel.path, false);
        });
      }
    ],
    onRuntimeInitialized: () => {
      const stream = options.FS.getStream(0);
      stream.stream_ops = {
        ...stream.stream_ops,
        poll: () => 4 | (queues.get('qmp').length ? 1 : 0)
      };
      hostBridge('runtime', {
        crossOriginIsolated,
        shared: options.HEAPU8.buffer instanceof SharedArrayBuffer,
        memoryBytes: options.HEAPU8.buffer.byteLength
      });
    }
  };
  globalThis.qemu = await createQemu(options);
  globalThis.bridgeReady = true;
}
