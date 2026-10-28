import {Device,Module} from '../../core/index.js';import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';import {buildRFID} from './assembly.js';import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.rfid',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){buildRFID(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.rfid.grove',name:spec.name+' · real HY2.0 cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildRFID,options);}}
export {spec,defaults,configurations,configurationSchema};export default Model;
