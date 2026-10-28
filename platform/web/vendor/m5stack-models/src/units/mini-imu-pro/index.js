import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildMiniIMUPro} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.mini-imu-pro',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(){buildMiniIMUPro(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.mini-imu-pro.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildMiniIMUPro,options);}}
export {spec};export default Model;
