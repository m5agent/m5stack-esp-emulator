// All observation traffic shares one bounded pool. No write transport exists.
export class ReadPool {
  constructor(limit = 4) { this.limit = limit; this.active = 0; this.queue = []; this.closed = false; }
  run(task) {
    if (this.closed) return Promise.reject(new DOMException('Closed', 'AbortError'));
    return new Promise((resolve, reject) => { this.queue.push({task, resolve, reject}); this.drain(); });
  }
  drain() {
    while (!this.closed && this.active < this.limit && this.queue.length) {
      const item = this.queue.shift();
      this.active++;
      Promise.resolve().then(item.task).then(item.resolve, item.reject).finally(() => { this.active--; this.drain(); });
    }
  }
  dispose() {
    this.closed = true;
    for (const item of this.queue.splice(0)) item.reject(new DOMException('Closed', 'AbortError'));
  }
}

export class ObservatoryAPI {
  constructor({token = '', fetchImpl = globalThis.fetch, timeout = 4000} = {}) {
    this.token = token; this.fetchImpl = (...args) => fetchImpl(...args); this.timeout = timeout;
    this.pool = new ReadPool(4); this.requests = new Set(); this.generation = 0;
  }
  response(path, options = {}) {
    if (options.method && options.method !== 'GET' || options.body !== undefined) return Promise.reject(new Error('展示页仅允许只读请求。'));
    if (!/^\/(?:api\/v1(?:\/|\?|$)|devices\/|platform\/units\/)/.test(path) || /[\\\r\n]/.test(path) || path.split('?')[0].split('/').some(x => x === '.' || x === '..')) return Promise.reject(new Error('无效的观察路径。'));
    const generation = this.generation;
    return this.pool.run(async () => {
      if (generation !== this.generation || options.signal?.aborted) throw new DOMException('Stale', 'AbortError');
      const controller = new AbortController(), headers = new Headers(options.headers);
      // Only API requests receive the service credential.
      if (this.token && path.startsWith('/api/v1/')) headers.set('Authorization', `Bearer ${this.token}`);
      const cancel = () => controller.abort();
      options.signal?.addEventListener('abort', cancel, {once: true});
      const timer = setTimeout(cancel, this.timeout);
      this.requests.add(controller);
      try {
        const response = await this.fetchImpl(path, {method: 'GET', headers, signal: controller.signal, cache: 'no-store', credentials: 'omit', redirect: 'error'});
        if (!response.ok && response.status !== 304) {
          let message = `读取失败（${response.status}）`;
          try { const body = await response.json(); message = body?.error?.message || message; } catch {}
          throw Object.assign(new Error(message), {status: response.status});
        }
        // Consume bodies inside the pool so the limit includes transfers.
        const blob = response.status === 304 ? null : await response.blob();
        if (generation !== this.generation || controller.signal.aborted) throw new DOMException('Stale', 'AbortError');
        return {status: response.status, headers: response.headers, blob};
      } finally {
        clearTimeout(timer); options.signal?.removeEventListener('abort', cancel); this.requests.delete(controller);
      }
    });
  }
  async json(path, options) {
    const generation = this.generation;
    const result = await this.response(path, options);
    if (!result.blob) throw new Error('观察响应为空。');
    const body = JSON.parse(await result.blob.text());
    if (generation !== this.generation || options?.signal?.aborted) throw new DOMException('Stale', 'AbortError');
    return body;
  }
  invalidate() { this.generation++; for (const request of this.requests) request.abort(); }
  dispose() { this.invalidate(); this.pool.dispose(); }
}
