import { ThreeDeviceShell } from './three-device-viewer.js?v=20261022e';
import { StickS3 } from './vendor/sticks3/src/devices/sticks3/StickS3.js';

export class StickS3ThreeShell extends ThreeDeviceShell {
  constructor(host, device) {
    super(host, device, {
      rendererId: 'sticks3-three',
      modelFactory: () => new StickS3({ pixelEffect: true }),
      controlMap: {
        btnA: 'a',
        btnB: 'b',
        btnPWR: 'power'
      },
      ledTarget: 'irTx'
    });
  }
}
