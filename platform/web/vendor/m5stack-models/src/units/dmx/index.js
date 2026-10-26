import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildDMX} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.dmx',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyT:'termination',KeyR:'xlr-release'}};
 build(){buildDMX(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.dmx.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildDMX,options);}
}
export {spec} from './dimensions.js';
export default Model;
