import {Device, Display, materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {cadButton, physicalButton} from '../../modeling/actuators.js';
import {slab} from '../../modeling/parts.js';
import {addAssembly} from './assembly.js';
import {addKeyboard, KEYMAP, MATRIX} from './keyboard.js';
import {DIM} from './dimensions.js';
import {addStickers} from './stickers.js';
import geometryData from './geometry-data.js';

export class Cardputer extends Device {
  static meta = {
    id: 'm5stack.cardputer',
    name: 'Cardputer',
    sku: 'K132',
    vendor: 'M5Stack',
    size: DIM.body,
    keymap: KEYMAP,
    hardware: {
      mcu: 'ESP32-S3FN8',
      flashMb: 8,
      psramMb: 0,
      keyboard: MATRIX,
    },
  };

  build() {
    const parts = addCadParts(this, geometryData, {
      case: materials.plastic(0xe2e4df, {roughness: 0.74}),
      base: materials.plastic(0xc9cbc7, {roughness: 0.8}),
      key: materials.plastic(0x202624, {roughness: 0.91}),
      stamp: materials.plastic(0x262c28, {roughness: 0.76}),
    });
    const {x, y, z, w, h} = DIM.display;
    const back = slab(this.body, w + 0.85, h + 0.85, 1.2, 0.48, [x, y, z - 1.25],
      materials.glossy(0x0a1212, {roughness: 0.24}), [], 0.04);
    back.name = 'LCD black glass border and backing';
    this.add(new Display({
      id: 'lcd',
      label: '1.14-inch TFT',
      width: 240,
      height: 135,
      size: [w, h],
      position: [x, y, z],
      glass: {intensity: 0.13, roughness: 0.22},
      meta: {
        controller: 'ST7789V2',
        role: 'external-framebuffer',
        gpio: {backlight: 38, reset: 33, dc: 34, mosi: 35, sclk: 36, cs: 37},
      },
    }));
    addKeyboard(this, parts['keyboard-membrane']);
    cadButton(this, {
      source: parts['upper-housing'],
      id: 'boot', label: 'G0 / Boot', position: [20.8, 26.6, 2.72],
      face: 'top', w: 5.6, h: 7.6, r: 0.7, depth: 1.4, travel: 0.22,
      meta: {gpio: 0, activeLow: true},
    });
    cadButton(this, {
      source: parts['upper-housing'],
      id: 'reset', label: 'Reset', position: [-26.65, 26.2, 2.65],
      face: 'top', w: 5.6, h: 7.6, r: 0.7, depth: 1.4, travel: 0.22,
      meta: {signal: 'EN'},
    });
    physicalButton(this, {
      mesh: parts['power-slide'],
      id: 'power', label: 'Power slider',
      axis: [-1, 0, 0], travel: 1.2, latching: true,
      isolateMaterials: true,
      meta: {
        surfaceCenter: [10.1, 27, 2.65],
        surfaceFace: 'top',
        mechanism: 'slide',
        detents: ['OFF', 'ON'],
        electricalBehavior: false,
      },
    });
    addAssembly(this);
    addStickers(this);
  }
}

export default Cardputer;
