import { ThreeDeviceShell } from './three-device-viewer.js';
import { CoreS3 } from './vendor/sticks3/src/devices/cores3/CoreS3.js';

export class CoreS3ThreeShell extends ThreeDeviceShell {
  constructor(host, device) {
    super(host, device, {
      rendererId: 'cores3-three',
      modelFactory: () => new CoreS3({ touch: true, pixelEffect: true }),
      controlMap: {
        power: 'power'
      },
      defaultView: 'iso',
      fitPadding: 1.35
    });
  }
}
