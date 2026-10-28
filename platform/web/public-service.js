import { normalizeServiceUrl } from './public-config.js';
import { FirmwareUploadClient } from './firmware-upload.js';

// This client only addresses the explicitly selected service. Firmware URLs are
// downloaded separately without credentials; they are never server fetch targets.
export class PublicDeviceService {
  constructor(url, {token = '', fetchImpl = globalThis.fetch, pageUrl} = {}) {
    this.url = normalizeServiceUrl(url, {pageUrl});
    if (!this.url) throw new Error('请先连接仿真服务。');
    this.token = token;
    this.fetchImpl = (...args) => fetchImpl(...args);
    this.uploads = new FirmwareUploadClient({fetchImpl: (path, options) => this.fetch(path, options), tokenProvider: () => this.token});
  }

  fetch(path, options = {}) {
    if (!/^\/api\/v1(?:\/|\?|$)/.test(path) || /[\\\r\n]/.test(path)) throw new Error('无效的服务请求。');
    const target = new URL(this.url + path);
    const apiBase = new URL(this.url + '/api/v1').pathname;
    if (target.origin !== new URL(this.url).origin || !(target.pathname === apiBase || target.pathname.startsWith(apiBase + '/'))) throw new Error('服务请求不能离开 API 路径。');
    const headers = new Headers(options.headers);
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    return this.fetchImpl(target.href, {...options, headers, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer'});
  }

  async request(path, {body, ...options} = {}) {
    const headers = new Headers(options.headers);
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    const response = await this.fetch(path, {...options, headers, body: body === undefined ? undefined : JSON.stringify(body)});
    let content;
    try { content = await response.json(); }
    catch (cause) {
      // A successful POST can allocate a session before its receipt is lost or
      // truncated. The caller must retain the original idempotency key.
      const error = new Error(`服务返回了无效的 JSON（${response.status}）。`, {cause});
      error.code = 'invalid_service_response';
      error.status = response.status;
      error.requestId = response.headers.get('X-Request-ID');
      error.outcomeUnknown = true;
      throw error;
    }
    if (!response.ok) {
      const error = new Error(content?.error?.message || `服务请求失败（${response.status}）`);
      error.code = content?.error?.code;
      error.status = response.status;
      error.requestId = response.headers.get('X-Request-ID');
      error.outcomeUnknown = response.status >= 500;
      throw error;
    }
    return content;
  }

  devices(options) { return this.request('/api/v1/devices', options); }
  units(id, options) { return this.request(`/api/v1/units?device_id=${encodeURIComponent(id)}`, options); }
  session(id, options) { return this.request(`/api/v1/sessions/${encodeURIComponent(id)}`, options); }
  serial(id, offset = 0, options) { return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/serial?offset=${offset}&limit=65536`, options); }
  input(id, body, options) { return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/input`, {...options, method: 'POST', body}); }

  async importFirmware(file, deviceId, {signal, onProgress} = {}) {
    const {artifact} = await this.uploads.upload({file, deviceId, signal, onProgress});
    const result = await this.uploads.importPackage({deviceId, artifactId: artifact.artifact_id, signal});
    if (!result.firmware_id || result.device_id !== deviceId) {
      throw new Error(result.issues?.map(item => item.message || item.code).join('；') || '固件未通过该设备的兼容性检查。');
    }
    return result;
  }

  create({deviceId, firmwareId, units = [], idempotencyKey, signal}) {
    return this.request('/api/v1/sessions', {method: 'POST', signal,
      body: {device_id: deviceId, ...(firmwareId ? {firmware_id: firmwareId} : {}), ttl_seconds: 600,
        ...(units.length ? {units} : {}), ...(idempotencyKey === undefined ? {} : {idempotency_key: idempotencyKey})}});
  }

  async evidence(id, options) {
    const response = await this.fetch(`/api/v1/sessions/${encodeURIComponent(id)}/evidence`, options);
    if (!response.ok) throw new Error(`证据导出失败（${response.status}）`);
    return response.blob();
  }

  stop(id, options) { return this.request(`/api/v1/sessions/${encodeURIComponent(id)}?purge=0`, {...options, method: 'DELETE'}); }
}
