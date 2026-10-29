// MIT. K125 actual visible exterior/inputs/light/connectors;firmware and sensing external.
import {Device} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
import {spec} from './dimensions.js';
class AtomS3U extends Device{
 static meta={id:'m5stack.atoms3u',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.nominalMm,keymap:{Space:'button'},scope:'visual-only'};
 build(options={}){if(options.artwork!==undefined&&typeof options.artwork!=='boolean')throw new TypeError('artwork must be boolean');buildAssembly(this);addStickers(this);}
}
export {AtomS3U as Model};
export {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export default AtomS3U;
