import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildHBridge}from'./assembly.js';import{TerminalPlug}from'./TerminalPlug.js';import{spec}from'./dimensions.js';
function validate(options){if(options.capacitor===true&&options.terminalPlug!==true)throw new TypeError('capacitor:true requires terminalPlug:true');}
function attachSuppliedTerminal(host,options){if(options.terminalPlug===true)host.port('terminal').attach(new TerminalPlug({capacitor:options.capacitor===true,artwork:options.artwork}));}
export class Model extends Device{static meta={id:'m5stack.unit.hbridge-v11',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){validate(options);buildHBridge(this,options);attachSuppliedTerminal(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.hbridge-v11.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){validate(options);buildGroveModuleAssembly(this,host=>buildHBridge(host,options),options);attachSuppliedTerminal(this,options);}}
export{TerminalPlug,spec};export default Model;
