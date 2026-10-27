import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildOled} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.oled',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildOled(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.oled.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildOled,options);}
}
export {spec};
export default Model;
