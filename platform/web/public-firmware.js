import { Sha256 } from './sha256.js';

export const DEFAULT_MAX_FIRMWARE_BYTES = 64 * 1024 * 1024;

export class PublicFirmwareError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'PublicFirmwareError';
    this.code = code;
  }
}

export function sensitiveQueryKey(key) {
  return /^(?:token|access[_-]?token|auth(?:orization)?|api[_-]?key|key|secret|password|signature|x-amz-.+|x-goog-.+)$/i.test(key);
}

function isLoopback(hostname) {
  return ['localhost', '127.0.0.1', '[::1]'].includes(hostname.toLowerCase());
}

export function normalizeFirmwareUrl(value, { pageUrl = globalThis.location?.href || 'https://example.invalid/' } = {}) {
  if (typeof value !== 'string' || !value.trim() || value.length > 8192 || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new PublicFirmwareError('invalid_firmware_url', '请输入完整的 HTTPS 固件下载地址。');
  }
  let url;
  try { url = new URL(value.trim()); } catch {
    throw new PublicFirmwareError('invalid_firmware_url', '请输入完整的 HTTPS 固件下载地址。');
  }
  if (url.username || url.password || [...url.searchParams.keys()].some(sensitiveQueryKey)) {
    throw new PublicFirmwareError('firmware_credentials', '固件链接不能包含凭据或签名参数，请使用公开下载地址或本地文件。');
  }
  if (url.hash) throw new PublicFirmwareError('firmware_fragment', '固件下载地址不能包含片段，请在 SHA-256 字段单独填写校验值。');
  if (['github.com', 'www.github.com'].includes(url.hostname.toLowerCase())) {
    // GitHub HTML blob pages do not expose firmware bytes. Preserve the entire
    // ref/path suffix: GitHub refs may themselves contain slashes.
    url.protocol = 'https:';
    url.hostname = 'github.com';
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length >= 5 && ['blob', 'raw'].includes(parts[2])) {
      url.hostname = 'raw.githubusercontent.com';
      url.pathname = '/' + [...parts.slice(0, 2), ...parts.slice(3)].join('/');
      url.search = '';
    }
  }
  const localDevelopment = new URL(pageUrl).protocol === 'http:' && isLoopback(url.hostname);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && localDevelopment)) {
    throw new PublicFirmwareError('insecure_firmware_url', '公开站点只接受 HTTPS 固件地址；HTTP 地址会被浏览器拦截。');
  }
  return url.href;
}

export function normalizeFirmwareSha256(value) {
  if (value == null || value === '') return null;
  if (typeof value !== 'string' || !/^[a-fA-F0-9]{64}$/.test(value)) {
    throw new PublicFirmwareError('invalid_sha256', 'SHA-256 必须是 64 位十六进制字符串。');
  }
  return value.toLowerCase();
}

function aborted(signal) {
  if (signal?.aborted) throw signal.reason || new DOMException('下载已取消。', 'AbortError');
}

function firmwareName(url) {
  let name = new URL(url).pathname.split('/').pop() || 'firmware.bin';
  try { name = decodeURIComponent(name); } catch { /* Retain escaped name. */ }
  name = name.replace(/[^\p{L}\p{N}._-]/gu, '_').slice(0, 120);
  return name || 'firmware.bin';
}

export async function downloadFirmware(value, {
  signal,
  maxBytes = DEFAULT_MAX_FIRMWARE_BYTES,
  expectedSha256 = null,
  onProgress = () => {},
  fetchImpl = globalThis.fetch,
  pageUrl,
} = {}) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0 || maxBytes > DEFAULT_MAX_FIRMWARE_BYTES) {
    throw new PublicFirmwareError('invalid_size_limit', '固件下载上限必须在 1 字节至 64 MiB 之间。');
  }
  const url = normalizeFirmwareUrl(value, { pageUrl });
  const expected = normalizeFirmwareSha256(expectedSha256);
  aborted(signal);
  let response;
  try {
    response = await fetchImpl(url, {
      signal, mode: 'cors', credentials: 'omit', referrerPolicy: 'no-referrer',
      redirect: 'follow', cache: 'no-store',
    });
  } catch (error) {
    aborted(signal);
    throw new PublicFirmwareError('firmware_cors_or_network', '无法下载固件。请确认地址可公开访问并允许跨域（CORS），或改用本地文件。');
  }
  aborted(signal);
  if (!response.ok || response.type === 'opaque') {
    throw new PublicFirmwareError('firmware_http', `固件下载失败（HTTP ${response.status || '不可读'}）。`);
  }
  const finalUrl = normalizeFirmwareUrl(response.url || url, { pageUrl });
  const type = (response.headers.get('content-type') || '').toLowerCase();
  if (type.includes('text/html')) throw new PublicFirmwareError('firmware_html', '下载结果是网页，请使用原始二进制文件链接。');
  const declared = Number(response.headers.get('content-length')) || null;
  if (declared && declared > maxBytes) {
    await response.body?.cancel();
    throw new PublicFirmwareError('firmware_too_large', '固件超过下载大小上限（64 MiB 或当前设置）。');
  }
  const chunks = [];
  const hasher = new Sha256();
  let received = 0;
  const reader = response.body?.getReader();
  function accept(chunk) {
    aborted(signal);
    received += chunk.byteLength;
    if (received > maxBytes) throw new PublicFirmwareError('firmware_too_large', '固件超过下载大小上限（64 MiB 或当前设置）。');
    chunks.push(chunk);
    hasher.update(chunk);
    onProgress({ received, total: declared, phase: 'downloading' });
  }
  try {
    if (reader) {
      while (true) {
        aborted(signal);
        const { done, value: chunk } = await reader.read();
        if (done) break;
        accept(chunk);
      }
    } else accept(new Uint8Array(await response.arrayBuffer()));
  } catch (error) {
    try { await reader?.cancel(); } catch { /* Do not hide the original failure. */ }
    aborted(signal);
    if (error instanceof PublicFirmwareError) throw error;
    throw new PublicFirmwareError('firmware_stream', '固件传输中断，请重试或使用本地文件。');
  } finally {
    reader?.releaseLock();
  }
  aborted(signal);
  if (!received) throw new PublicFirmwareError('empty_firmware', '下载的固件为空。');
  const sha256 = hasher.hex();
  if (expected && sha256 !== expected) throw new PublicFirmwareError('sha256_mismatch', '固件 SHA-256 与预期不一致，未加载固件。');
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  onProgress({ received, total: received, phase: 'downloaded' });
  return { bytes: bytes.buffer, name: firmwareName(finalUrl), size: received, sha256, url: finalUrl };
}
