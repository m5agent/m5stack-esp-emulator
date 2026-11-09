import {Device} from '../../core/index.js';
import {addCoreMatrixAssembly} from './assembly.js';
import {spec} from './dimensions.js';
import {addNativeHousing} from './native.js';

export {spec};
export const defaults = {artwork: true};
export const configurations = {};

export class CoreMatrix extends Device {
  static meta = {
    id: 'm5stack.corematrix', name: spec.name, sku: spec.sku, vendor: 'M5Stack',
    size: spec.size, keymap: {KeyA: 'btnA', KeyB: 'btnB', KeyC: 'btnC', KeyP: 'power'},
  };

  build() {
    this.coreMatrixHousing = addNativeHousing(this);
    addCoreMatrixAssembly(this);
  }
}

export const Model = CoreMatrix;
export default CoreMatrix;
