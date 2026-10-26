import { definePlugin } from '../../core/registry.js';
import { StickS3, DIM, HAT2_PINS, GROVE_PINS, USB_PINS } from './StickS3.js';

export { StickS3, DIM, HAT2_PINS, GROVE_PINS, USB_PINS };

/** `registerPlugin(sticks3Plugin)` to create the device by id: `createDevice('m5stack.sticks3')`. */
export const sticks3Plugin = definePlugin({
  name: 'm5stack.sticks3',
  devices: [StickS3],
});
