import {Device,Module} from '../../core/index.js';import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';import {buildENVII} from './assembly.js';import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.env-ii',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){buildENVII(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.env-ii.grove',name:spec.name+' · real HY2.0 cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildENVII,options);}}
export {spec,defaults,configurations,configurationSchema};export default Model;
