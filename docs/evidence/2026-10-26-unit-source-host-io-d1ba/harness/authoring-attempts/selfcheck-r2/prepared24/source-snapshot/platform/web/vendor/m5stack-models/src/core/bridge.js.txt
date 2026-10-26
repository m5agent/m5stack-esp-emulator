// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
/**
 * Connect a device to a simulator running elsewhere (Web Worker, iframe,
 * WebSocket, WASM glue…) using plain, structured-clone-friendly messages.
 *
 *   device → simulator   { type: 'input', kind, id, action, … }
 *                        { type: 'imu', accel, gyro }        (when imuRate > 0)
 *                        { type: 'reply', id, result | error } (for commands with `id`)
 *   simulator → device   any command accepted by `device.handle()`, e.g.
 *                        { type: 'display', target: 'lcd', format: 'rgb565', x, y, w, h, data }
 *                        { type: 'vibrate', pattern: [80, 40, 80] }
 *                        { type: 'imu', target: 'imu', id: 7 }  → reply with the reading
 *
 *   const worker = new Worker('./firmware.js', { type: 'module' });
 *   const bridge = createBridge(device, { send: (m, t) => worker.postMessage(m, t) });
 *   worker.onmessage = (e) => bridge.receive(e.data);
 */
export function createBridge(device, { send, imuRate = 0, imu = 'imu', onError = console.error } = {}) {
  if (typeof send !== 'function') throw new Error('createBridge: "send" function is required');
  const offs = [device.on('input', (evt) => send({ type: 'input', ...evt }))];

  let timer = null;
  const imuComponent = imuRate > 0 ? device.find(imu, 'imu') : null;
  if (imuComponent) {
    timer = setInterval(() => send({ type: 'imu', ...imuComponent.read() }), 1000 / imuRate);
  }

  function receive(msg) {
    try {
      const result = device.handle(msg);
      if (msg?.id != null) send({ type: 'reply', id: msg.id, result: result ?? null });
      return result;
    } catch (err) {
      if (msg?.id != null) send({ type: 'reply', id: msg.id, error: String(err?.message ?? err) });
      else onError(err);
      return undefined;
    }
  }

  return {
    receive,
    dispose() {
      offs.forEach((off) => off());
      clearInterval(timer);
    },
  };
}
