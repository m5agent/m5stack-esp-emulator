// MIT. Original C123 visual host. Firmware, buses, sensing and device behavior belong downstream.
import {Device} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
import {spec} from './dimensions.js';
class AtomS3 extends Device{
 static meta={id:'m5stack.atoms3',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.nativeMm,keymap:{Space:'button'},scope:'visual-only'};
 build(options={}){if(options.artwork!==undefined&&typeof options.artwork!=='boolean')throw new TypeError('artwork must be boolean');buildAssembly(this);addStickers(this);}
}
export {AtomS3 as Model};
export {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export default AtomS3;
