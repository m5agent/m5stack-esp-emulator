import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildMiniBPSV11} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.mini-bps-v11',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildMiniBPSV11(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.mini-bps-v11.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildMiniBPSV11,options);}
}
export {spec};
export default Model;
