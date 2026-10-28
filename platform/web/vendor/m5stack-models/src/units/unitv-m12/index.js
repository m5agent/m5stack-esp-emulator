import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildUnitVM12}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unitv-m12',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyA:'buttonA',KeyB:'buttonB'}};build(){buildUnitVM12(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unitv-m12.grove',name:spec.name,sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildUnitVM12,options);}}
export{spec,configurations,defaults,configurationSchema}from'./dimensions.js';export default Model;
