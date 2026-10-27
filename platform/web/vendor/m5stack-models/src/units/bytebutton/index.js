import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildBytebutton} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.bytebutton',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Digit1:'press-1',Digit2:'press-2',Digit3:'press-3',Digit4:'press-4',Digit5:'press-5',Digit6:'press-6',Digit7:'press-7',Digit8:'press-8'}};
 build(){buildBytebutton(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.bytebutton.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildBytebutton,options);}
}
export {spec,CHANNELS} from './dimensions.js';
export default Model;
