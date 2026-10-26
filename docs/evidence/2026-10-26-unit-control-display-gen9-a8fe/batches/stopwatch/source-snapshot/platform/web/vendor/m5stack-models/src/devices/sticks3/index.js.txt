// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import { definePlugin } from '../../core/registry.js';
import { StickS3, DIM, HAT2_PINS, GROVE_PINS, USB_PINS } from './StickS3.js';

export { StickS3, DIM, HAT2_PINS, GROVE_PINS, USB_PINS };

/** `registerPlugin(sticks3Plugin)` to create the device by id: `createDevice('m5stack.sticks3')`. */
export const sticks3Plugin = definePlugin({
  name: 'm5stack.sticks3',
  devices: [StickS3],
});
