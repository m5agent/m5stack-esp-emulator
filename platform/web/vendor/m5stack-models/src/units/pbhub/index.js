import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildPbHub} from './assembly.js';
import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.pbhub',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){buildPbHub(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.pbhub.grove',name:spec.name+' · physical Grove cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildPbHub,options);}}
export {spec,defaults,configurations,configurationSchema};export default Model;
