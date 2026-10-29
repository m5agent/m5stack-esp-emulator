// MIT. Actual C126-CAM exterior/input/light/connection; camera data and firmware external.
import {Device} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
import {spec} from './dimensions.js';
class AtomS3RCam extends Device{
 static meta={id:'m5stack.atoms3r-cam',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.nativeMm,keymap:{},scope:'visual-only'};
 build(options={}){if(options.artwork!==undefined&&typeof options.artwork!=='boolean')throw new TypeError('artwork must be boolean');buildAssembly(this);addStickers(this);}
}
export {AtomS3RCam as Model};
export {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export default AtomS3RCam;
