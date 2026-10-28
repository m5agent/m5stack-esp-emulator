import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildWeight} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.weight',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};
 build(options={}){buildWeight(this);if(options.terminalPlug===true)this.get('terminal').attach(new TerminalPlug());}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.weight.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildWeight,options);if(options.terminalPlug===true)this.get('terminal').attach(new TerminalPlug());}
}
export {TerminalPlug,spec};export default Model;
