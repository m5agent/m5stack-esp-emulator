import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildJoystick2} from './assembly.js';
import {spec} from './dimensions.js';

export class Model extends Device{
 static meta={id:'m5stack.unit.joystick2',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(){buildJoystick2(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.joystick2.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildJoystick2,options);}
}
export {spec};
export default Model;
