import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildGesture} from './assembly.js';
import {spec} from './dimensions.js';

export class Model extends Device{
 static meta={id:'m5stack.unit.gesture',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildGesture(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.gesture.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildGesture,options);}
}
export {spec};
export default Model;
