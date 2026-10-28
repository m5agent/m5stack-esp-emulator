import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildGlass}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.glass',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyA:'button-a',KeyB:'button-b'}};build(){buildGlass(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.glass.grove',name:spec.name,sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildGlass,options);}}
export{spec,configurations,defaults,configurationSchema}from'./dimensions.js';export default Model;
