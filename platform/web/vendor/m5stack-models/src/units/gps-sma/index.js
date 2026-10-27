import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildGPSSMA} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.gps-sma',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){buildGPSSMA(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.gps-sma.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildGPSSMA(h,options),options);}}
export {Antenna} from './Antenna.js';export {spec};export default Model;
