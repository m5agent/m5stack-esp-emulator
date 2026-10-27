import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {build2Relay} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {spec} from './dimensions.js';
function attachSuppliedTerminals(host,options){if(options.terminalPlug===true)for(const channel of spec.channels)host.port(`terminal-${channel.number}`).attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.2relay',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){build2Relay(this);attachSuppliedTerminals(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.2relay.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,build2Relay,options);attachSuppliedTerminals(this,options);}
}
export {TerminalPlug,spec};
export default Model;
