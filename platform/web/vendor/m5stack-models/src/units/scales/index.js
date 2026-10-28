import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildScales}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.scales',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'tare'}};build(){buildScales(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.scales.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildScales,options);}}
export{spec};export default Model;
