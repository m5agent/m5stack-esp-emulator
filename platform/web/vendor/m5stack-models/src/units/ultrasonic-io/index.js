import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildUltrasonicIO} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.ultrasonic-io',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildUltrasonicIO(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.ultrasonic-io.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildUltrasonicIO(h,options),options);}}
export {spec};export default Model;
