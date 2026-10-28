import { normalizeFirmwareUrl, normalizeFirmwareSha256, sensitiveQueryKey } from './public-firmware.js';

export class PublicConfigError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'PublicConfigError';
    this.code = code;
  }
}

export function siteRoot(moduleUrl = import.meta.url) {
  return new URL('../../', moduleUrl);
}

export function assetUrl(path, root = siteRoot()) {
  if (typeof path !== 'string' || !path || path.startsWith('//') || /[\u0000-\u001f\\]/.test(path)) {
    throw new PublicConfigError('invalid_asset', '无效的站点资源路径。');
  }
  const base = new URL(root);
  const result = path.startsWith(base.pathname)
    ? new URL(path, base.origin)
    : new URL(path.replace(/^\/+/, ''), base);
  if (result.origin !== base.origin || !result.pathname.startsWith(base.pathname)) {
    throw new PublicConfigError('invalid_asset', '资源路径不能离开当前站点。');
  }
  return result.href;
}

const ALIASES = Object.freeze({
  'm5cores3': 'cores3', 'core-s3': 'cores3', 'm5core2': 'core2', 'core-2': 'core2',
  'm5sticks3': 'sticks3', 'stick-s3': 'sticks3', 'm5atoms3r': 'atoms3r', 'atom-s3r': 'atoms3r',
  'cardputeradv': 'cardputer-adv', 'cardputer-advanced': 'cardputer-adv',
  'm5tab5': 'tab5', 'm5stamplc': 'stamplc', 'stamp-plc': 'stamplc',
  'nano-c6': 'nanoc6', 'm5nanoc6': 'nanoc6', 'nesson1': 'nesso-n1',
  'paper-mono': 'papermono', 'paper-color': 'papercolor', 'stack-chan': 'stackchan',
  'stop-watch': 'stopwatch', 'cardputerzero': 'cardputer-zero',
  'm5papers3': 'papers3', 'paper-s3': 'papers3', 'm5stack-c139': 'papers3',
});

export function resolveDevice(value, catalog, { defaultId = 'cores3' } = {}) {
  const devices = Array.isArray(catalog) ? catalog : catalog?.devices;
  if (!Array.isArray(devices) || !devices.length) throw new PublicConfigError('invalid_catalog', '设备目录不可用。');
  const requested = value == null || value === '' ? defaultId : String(value).trim().toLowerCase();
  const canonical = ALIASES[requested] || requested.replace(/^devices\//, '');
  const device = devices.find(item => item.id === canonical || item.path === canonical || `devices/${item.path}` === canonical);
  if (!device) {
    throw new PublicConfigError('unknown_device', '链接指定的设备尚未收录，请从设备列表选择。PaperS3 与 PaperMono 是不同设备，不能互换固件。');
  }
  return device;
}

export function normalizeServiceUrl(value, { pageUrl = globalThis.location?.href || 'https://example.invalid/' } = {}) {
  if (value == null || value === '') return '';
  let url;
  try { url = new URL(value); } catch { throw new PublicConfigError('invalid_service_url', '请输入完整的 HTTPS Device Service 地址。'); }
  const development = new URL(pageUrl).protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && development)) {
    throw new PublicConfigError('insecure_service_url', '公开站点需要 HTTPS Device Service，HTTP 服务只供本地开发。');
  }
  if (url.username || url.password || url.search || url.hash || /[\u0000-\u001f\\]/.test(value)) {
    throw new PublicConfigError('service_credentials', '服务地址不能包含账号、查询参数或片段；凭据请在连接面板中填写。');
  }
  return url.href.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
}

export function parseLaunchConfig(search, catalog, { pageUrl = globalThis.location?.href || 'https://example.invalid/' } = {}) {
  const params = new URLSearchParams(search);
  const warnings = [];
  if ([...params.keys()].some(sensitiveQueryKey)) warnings.push('分享链接中的凭据参数已忽略，请在连接面板中填写。');
  for (const key of ['device', 'firmware', 'sha256', 'service', 'mode', 'autostart']) {
    if (params.getAll(key).length > 1) throw new PublicConfigError('duplicate_parameter', '分享链接含重复参数，请重新生成。');
  }
  const mode = params.get('mode') || 'auto';
  if (!['auto', 'browser', 'service', 'model'].includes(mode)) throw new PublicConfigError('invalid_mode', '不支持的运行模式。');
  if (params.has('autostart') && !['0', '1'].includes(params.get('autostart'))) throw new PublicConfigError('invalid_autostart', 'autostart 只接受 0 或 1。');
  return {
    device: resolveDevice(params.get('device'), catalog),
    firmware: params.has('firmware') ? normalizeFirmwareUrl(params.get('firmware'), { pageUrl }) : null,
    sha256: normalizeFirmwareSha256(params.get('sha256')),
    serviceUrl: normalizeServiceUrl(params.get('service'), { pageUrl }),
    mode, autostart: mode !== 'model' && params.get('autostart') !== '0', warnings,
  };
}

export function buildShareUrl({ deviceId, firmware = null, sha256 = null, serviceUrl = '', mode = 'auto', autostart = true }, pageUrl = globalThis.location?.href) {
  const result = new URL(pageUrl);
  result.search = '';
  result.hash = '';
  if (typeof deviceId !== 'string' || !/^[a-z0-9-]+$/.test(deviceId)) throw new PublicConfigError('invalid_device', '设备标识无效。');
  result.searchParams.set('device', deviceId);
  if (firmware) result.searchParams.set('firmware', normalizeFirmwareUrl(firmware, { pageUrl }));
  if (sha256) result.searchParams.set('sha256', normalizeFirmwareSha256(sha256));
  if (serviceUrl) result.searchParams.set('service', normalizeServiceUrl(serviceUrl, { pageUrl }));
  if (mode !== 'auto') {
    if (!['browser', 'service', 'model'].includes(mode)) throw new PublicConfigError('invalid_mode', '不支持的运行模式。');
    result.searchParams.set('mode', mode);
  }
  if (!autostart) result.searchParams.set('autostart', '0');
  return result.href;
}
