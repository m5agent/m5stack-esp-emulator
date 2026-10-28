import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildESP32CAM}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.esp32cam',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{KeyK:'key'}};build(){buildESP32CAM(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.esp32cam.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildESP32CAM,options);}}
export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
