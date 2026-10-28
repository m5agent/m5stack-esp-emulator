import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildGroveToGrove} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.grove-to-grove',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(){buildGroveToGrove(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.grove-to-grove.grove',name:spec.name+' · PORT.B control cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildGroveToGrove,options);}}
export {spec};export default Model;
