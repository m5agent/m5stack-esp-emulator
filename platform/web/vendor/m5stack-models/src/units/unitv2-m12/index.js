import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildUnitV2M12} from './assembly.js';
import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unitv2-m12',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'user'}};build(options={}){buildUnitV2M12(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unitv2-m12.grove',name:spec.name+' · real HY2.0 cable',sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildUnitV2M12,options);}}
export {spec,defaults,configurations,configurationSchema};export default Model;
