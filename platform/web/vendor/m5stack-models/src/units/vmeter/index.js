import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildVMeter}from'./assembly.js';import{TerminalPlug}from'./TerminalPlug.js';import{spec}from'./dimensions.js';
function attachSuppliedTerminal(host,options){if(options.terminalPlug===true)host.port('terminal').attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.vmeter',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){buildVMeter(this);attachSuppliedTerminal(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.vmeter.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildVMeter,options);attachSuppliedTerminal(this,options);}
}
export{TerminalPlug,spec};export default Model;
