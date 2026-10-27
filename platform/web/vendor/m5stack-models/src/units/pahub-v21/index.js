import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildPahub} from './assembly.js';
import {spec} from './dimensions.js';

export class Model extends Device{
 static meta={id:'m5stack.unit.pahub-v21',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Digit1:'dip-1',Digit2:'dip-2',Digit3:'dip-3'}};
 build(){buildPahub(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.pahub-v21.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildPahub,options);}
}
export {spec};
export default Model;
