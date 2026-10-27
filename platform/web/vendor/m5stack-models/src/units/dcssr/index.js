import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildDCSSR} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {spec} from './dimensions.js';
function terminals(host,options){if(options.terminalPlug===true)for(const id of ['terminal-1','terminal-2'])host.port(id).attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.dcssr',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyA:'button'}};
 build(options={}){buildDCSSR(this);terminals(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.dcssr.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{KeyA:'button'}};
 build(options={}){buildGroveModuleAssembly(this,buildDCSSR,options);terminals(this,options);}
}
export {TerminalPlug,spec};
export default Model;
