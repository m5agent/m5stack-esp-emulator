import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildGPS} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.gps',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size};build(){buildGPS(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.gps.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildGPS(h),options);}}
export {spec,defaults,configurationSchema,configurations} from './dimensions.js';
export default Model;
