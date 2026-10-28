import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildTypecToGrove}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.typec-to-grove',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(){buildTypecToGrove(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.typec-to-grove.grove',name:spec.name,sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,buildTypecToGrove,options);}}
export{spec};export default Model;
