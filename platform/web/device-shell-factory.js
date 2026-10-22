import { M5DeviceShell } from './device-shell.js?v=20261022a';

export async function createDeviceShell(host, device) {
  const renderer = device.shell?.renderer;
  if (renderer === 'sticks3-three' || renderer === 'cores3-three') {
    try {
      if (renderer === 'cores3-three') {
        const { CoreS3ThreeShell } = await import('./cores3-viewer.js?v=20261022e');
        return new CoreS3ThreeShell(host, device);
      }
      const { StickS3ThreeShell } = await import('./sticks3-viewer.js?v=20261022e');
      return new StickS3ThreeShell(host, device);
    } catch (error) {
      console.warn(`${device.name} three.js renderer unavailable; using the generic shell.`, error);
      const shell = new M5DeviceShell(host, device);
      shell.host.querySelector('.device-shell-root')?.setAttribute('data-renderer-fallback', 'true');
      return shell;
    }
  }
  return new M5DeviceShell(host, device);
}
