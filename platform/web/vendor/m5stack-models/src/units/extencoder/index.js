import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildExtEncoder} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {spec} from './dimensions.js';
function attachPlug(host,options){if(options.terminalPlug===true)host.port('encoder').attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.extencoder',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){buildExtEncoder(this);attachPlug(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.extencoder.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildExtEncoder,options);attachPlug(this,options);}
}
export {TerminalPlug,spec};
export default Model;
