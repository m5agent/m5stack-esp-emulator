import { definePlugin } from '../../core/registry.js';
import { CoreS3 } from './CoreS3.js';

export const cores3Plugin = definePlugin({
  name: 'm5stack.cores3',
  devices: [CoreS3]
});
