import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildMiniIMU} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.mini-imu',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildMiniIMU(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.mini-imu.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildMiniIMU,options);}
}
export {spec};
export default Model;
