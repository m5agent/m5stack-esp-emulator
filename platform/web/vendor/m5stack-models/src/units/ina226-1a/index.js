import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildINA2261A}from'./assembly.js';import{TerminalPlug}from'./TerminalPlug.js';import{spec}from'./dimensions.js';
function attachSuppliedPlug(host,options){if(options.terminalPlug===true)host.port('terminal').attach(new TerminalPlug({artwork:options.artwork}));}
export class Model extends Device{static meta={id:'m5stack.unit.ina226-1a',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){buildINA2261A(this);attachSuppliedPlug(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.ina226-1a.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildINA2261A,options);attachSuppliedPlug(this,options);}}
export{TerminalPlug,spec};export default Model;
