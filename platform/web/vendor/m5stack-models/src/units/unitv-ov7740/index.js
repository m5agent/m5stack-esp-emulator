import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildUnitVOv7740} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unitv-ov7740',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyA:'buttonA',KeyB:'buttonB'}};build(options={}){buildUnitVOv7740(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unitv-ov7740.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildUnitVOv7740(h,options),options);}}
export {spec};export default Model;
