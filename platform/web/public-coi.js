import {siteRoot} from './public-config.js';

export const COI_SOURCE_COMMIT = '7b1d2a092d0d2dd2b7270b6f12f13605de26f214';
export const COI_SOURCE_SHA256 = 'e97bbac6017322d48aa54a5bc7ce473c725a4b7376ff245002e0ba71c3dcdd7e';
export const COI_WORKER_FILE = 'coi-serviceworker.js';
const preparations = new WeakMap();

export class PublicIsolationError extends Error {
  constructor(code, message, cause) {
    super(message, cause ? {cause} : undefined);
    this.name = 'PublicIsolationError';
    this.code = code;
  }
}

function isolationRoot(value, environment) {
  const root = new URL(value);
  const page = new URL(environment.location.href);
  if (root.origin !== page.origin || root.search || root.hash ||
      !root.pathname.endsWith('/') || !page.pathname.startsWith(root.pathname)) {
    throw new PublicIsolationError('coi_invalid_scope', '浏览器隔离资源必须位于当前项目的同源目录中。');
  }
  return root;
}

function ownsController(serviceWorker, workerUrl) {
  return serviceWorker.controller?.scriptURL === workerUrl;
}

function deadline(promise, timeoutMs, code) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new PublicIsolationError(code, '浏览器隔离准备超时，请重试或使用支持的浏览器。')), timeoutMs);
    }),
  ]).finally(() => clearTimeout(timer));
}

function waitForReadyAndControl(serviceWorker, workerUrl, timeoutMs) {
  let ready = false, timer, changed;
  return new Promise((resolve, reject) => {
    const check = () => { if (ready && ownsController(serviceWorker, workerUrl)) resolve(); };
    changed = check;
    serviceWorker.addEventListener('controllerchange', changed);
    timer = setTimeout(() => reject(new PublicIsolationError('coi_control_timeout', '项目隔离服务尚未接管页面，请重试。')), timeoutMs);
    Promise.resolve(serviceWorker.ready).then(() => { ready = true; check(); }, reject);
    check();
  }).finally(() => {
    clearTimeout(timer);
    serviceWorker.removeEventListener('controllerchange', changed);
  });
}

async function prepare({root, environment, timeoutMs, reload}) {
  const workerUrl = new URL(COI_WORKER_FILE, root).href;
  const key = `m5-public-coi:${root.pathname}:${COI_SOURCE_COMMIT}`;
  let storage;
  if (environment.crossOriginIsolated === true && typeof environment.SharedArrayBuffer === 'function') {
    try { environment.sessionStorage?.removeItem(key); } catch { /* Isolation already works without this optional cleanup. */ }
    return {isolated:true,reloading:false,root:root.href,workerUrl};
  }
  try { storage = environment.sessionStorage; }
  catch (cause) { throw new PublicIsolationError('coi_storage_unavailable', '浏览器无法保存隔离重载状态，请允许当前站点的会话存储。', cause); }
  if (!environment.isSecureContext) {
    throw new PublicIsolationError('coi_insecure_context', '浏览器固件运行需要 HTTPS 或本机安全上下文。');
  }
  const serviceWorker = environment.navigator?.serviceWorker;
  if (!serviceWorker?.register || !serviceWorker.addEventListener || !serviceWorker.removeEventListener) {
    throw new PublicIsolationError('coi_unavailable', '此浏览器环境无法启用共享内存，请使用支持 Service Worker 的浏览器。');
  }
  try {
    if (!storage || storage.getItem(key) === '1') {
      throw new PublicIsolationError('coi_isolation_failed', '页面重载后仍未启用共享内存，请检查浏览器设置或重新打开此页面。');
    }
  } catch (cause) {
    if (cause instanceof PublicIsolationError) throw cause;
    throw new PublicIsolationError('coi_storage_unavailable', '浏览器无法保存隔离重载状态，请允许当前站点的会话存储。', cause);
  }
  let registration;
  try {
    registration = await deadline(serviceWorker.register(workerUrl, {scope:root.href,updateViaCache:'none'}), timeoutMs, 'coi_registration_timeout');
  } catch (cause) {
    if (cause instanceof PublicIsolationError) throw cause;
    throw new PublicIsolationError('coi_registration_failed', '无法准备当前项目的浏览器隔离资源。', cause);
  }
  if (registration.scope !== root.href) {
    throw new PublicIsolationError('coi_invalid_scope', '隔离服务的作用域与当前项目不匹配。');
  }
  await waitForReadyAndControl(serviceWorker, workerUrl, timeoutMs);
  // The pinned worker defaults to require-corp. Keep that policy explicit when
  // reusing an already active registration; never fall back to credentialless.
  serviceWorker.controller.postMessage({type:'coepCredentialless',value:false});
  try { storage.setItem(key, '1'); }
  catch (cause) { throw new PublicIsolationError('coi_storage_unavailable', '浏览器无法保存隔离重载状态，请允许当前站点的会话存储。', cause); }
  try { reload(); }
  catch (cause) {
    try { storage.removeItem(key); } catch { /* Retain the original reload error. */ }
    throw new PublicIsolationError('coi_reload_failed', '无法重新加载隔离后的页面。', cause);
  }
  return {isolated:false,reloading:true,root:root.href,workerUrl};
}

/** Call before accepting a local firmware File: the first visit can reload.
 * A reloading result is a navigation boundary, not permission to start WASM.
 * The SW entry must be exported at the project root; Pages cannot grant a
 * nested /platform/web/ script a broader scope through response headers.
 */
export async function ensurePublicIsolation({root=siteRoot(),environment=globalThis,timeoutMs=15000,reload} = {}) {
  const normalized = isolationRoot(root, environment);
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be positive');
  let pending = preparations.get(environment);
  if (!pending) { pending = new Map(); preparations.set(environment, pending); }
  if (pending.has(normalized.href)) return pending.get(normalized.href);
  const task = prepare({root:normalized,environment,timeoutMs,reload:reload || (() => environment.location.reload())});
  pending.set(normalized.href, task);
  try { return await task; }
  finally { if (pending.get(normalized.href) === task) pending.delete(normalized.href); }
}
