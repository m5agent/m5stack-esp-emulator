import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildPaHubV20}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.pahub-v20',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size};build(){buildPaHubV20(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.pahub-v20.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildPaHubV20(h),options);}}
export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
