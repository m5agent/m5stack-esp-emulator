import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildDAC2}from'./assembly.js';import{TerminalPlug}from'./TerminalPlug.js';import{spec}from'./dimensions.js';
function attachSuppliedTerminal(host,options){if(options.terminalPlug===true)host.port('terminal').attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.dac2',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){buildDAC2(this);attachSuppliedTerminal(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.dac2.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildDAC2,options);attachSuppliedTerminal(this,options);}
}
export{TerminalPlug,spec};export default Model;
