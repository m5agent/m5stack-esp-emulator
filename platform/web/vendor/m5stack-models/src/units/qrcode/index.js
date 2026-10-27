import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildQrCode} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.qrcode',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'button',KeyM:'mode'}};
 build(options={}){buildQrCode(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.qrcode.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildQrCode,options);}
}
export {spec} from './dimensions.js';export default Model;
