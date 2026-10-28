import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildUnitV2Usb} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unitv2-usb',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'user'}};build(options={}){buildUnitV2Usb(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unitv2-usb.grove',name:spec.name+' · real HY2.0 cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildUnitV2Usb,options);}}
export {Clip} from './accessories.js';export {spec};export default Model;
