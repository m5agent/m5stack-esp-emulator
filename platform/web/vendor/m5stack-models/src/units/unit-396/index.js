import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildUnit396}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unit-396',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){buildUnit396(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unit-396.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildUnit396(h,options),options);}}
export{TerminalPlug}from'./TerminalPlug.js';export{spec};export default Model;
