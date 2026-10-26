import { M5DeviceShell } from './device-shell.js?v=20261022a';

function genericShell(host, device) {
  const shell = new M5DeviceShell(host, device);
  let disposed = false;
  const on = shell.on.bind(shell);
  // The legacy DOM renderer predates the common PNG/lifecycle/input contract.
  // Give the fallback the same service surface so failed WebGL remains usable.
  shell.on = (type, callback) => {
    if (type === 'touch') {
      let held = false;
      return on(type, event => {
        const action = event.down ? (held ? 'move' : 'start') : 'end';
        held = event.down;
        callback({ ...event, action });
      });
    }
    if (type === 'control') return on(type, event => callback({
      ...event, key: ({power: 'p', key1: 'a', key2: 'b', key3: 'c', button: 'a'})[event.id] || event.id,
    }));
    return on(type, callback);
  };
  shell.setImage = async (image, sequence = shell.frameSeq + 1, commitGuard = () => true) => {
    if (disposed || !shell.canvas || !commitGuard()) return false;
    const bitmap = await createImageBitmap(image);
    try {
      if (disposed || !commitGuard()) return false;
      shell.canvas.width = bitmap.width;
      shell.canvas.height = bitmap.height;
      shell.canvas.getContext('2d').drawImage(bitmap, 0, 0);
      shell.frameSeq = sequence;
      shell.hideOverlay();
      return true;
    } finally { bitmap.close(); }
  };
  shell.dispose = () => {
    if (disposed) return;
    disposed = true;
    shell.listeners = {};
    host.replaceChildren();
  };
  host.querySelector('.device-shell-root')?.setAttribute('data-renderer-fallback', 'true');
  return shell;
}

export async function createDeviceShell(host, device, options = {}) {
  // Public visual models are loaded per device. A failed WebGL/model import
  // retains the existing renderer and ultimately the accessible generic shell.
  try {
    const { createModelShell, supportsModelShell } = await import('./model-shell.js?v=20261026h');
    if (supportsModelShell(device)) return await createModelShell(host, device, options);
  } catch (error) {
    console.warn(`${device.name} public visual model unavailable; using the existing shell.`, error);
  }
  const renderingDevice = options.live && device.shell?.reference_image
    ? { ...device, shell: { ...device.shell, reference_image: null } }
    : device;
  const renderer = device.shell?.renderer;
  if (renderer === 'sticks3-three' || renderer === 'cores3-three') {
    try {
      if (renderer === 'cores3-three') {
        const { CoreS3ThreeShell } = await import('./cores3-viewer.js?v=20261022e');
        return new CoreS3ThreeShell(host, renderingDevice);
      }
      const { StickS3ThreeShell } = await import('./sticks3-viewer.js?v=20261022e');
      return new StickS3ThreeShell(host, renderingDevice);
    } catch (error) {
      console.warn(`${device.name} three.js renderer unavailable; using the generic shell.`, error);
      return genericShell(host, renderingDevice);
    }
  }
  return genericShell(host, renderingDevice);
}
