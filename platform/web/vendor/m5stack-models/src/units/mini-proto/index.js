import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildMiniProto} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.mini-proto',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildMiniProto(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.mini-proto.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildMiniProto(h,options),options);}}
export {spec};
export default Model;
