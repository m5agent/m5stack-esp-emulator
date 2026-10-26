import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildRelay,TerminalPlug} from './assembly.js';
import {spec} from './dimensions.js';

/** U023 appearance only. terminalPlug selects the supplied removable accessory. */
export class Model extends Device{
 static meta={id:'m5stack.unit.relay',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){buildRelay(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.relay.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,host=>buildRelay(host,options),options);}
}
export {TerminalPlug,spec};
export default Model;
