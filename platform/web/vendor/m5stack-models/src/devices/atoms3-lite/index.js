// MIT. AtomS3 Lite C124 visual model, externally driven input/output only.
import {Device} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
import {spec} from './dimensions.js';
class AtomS3Lite extends Device{
 static meta={id:'m5stack.atoms3-lite',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.nativeMm,keymap:{Space:'button'},scope:'visual-only'};
 build(options={}){if(options.artwork!==undefined&&typeof options.artwork!=='boolean')throw new TypeError('artwork must be boolean');buildAssembly(this);addStickers(this);}
}
export {AtomS3Lite as Model};
export {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export default AtomS3Lite;
