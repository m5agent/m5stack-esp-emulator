import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildCamS3FiveMP} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.cams3-5mp',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildCamS3FiveMP(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.cams3-5mp.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildCamS3FiveMP,options);}
}
export {spec};
export default Model;
