import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildByteSwitch} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.byteswitch',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Digit1:'switch-1',Digit2:'switch-2',Digit3:'switch-3',Digit4:'switch-4',Digit5:'switch-5',Digit6:'switch-6',Digit7:'switch-7',Digit8:'switch-8'}};
 build(){buildByteSwitch(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.byteswitch.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildByteSwitch,options);}
}
export {spec,CHANNELS} from './dimensions.js';
export {ToggleButton} from './ToggleButton.js';
export default Model;
