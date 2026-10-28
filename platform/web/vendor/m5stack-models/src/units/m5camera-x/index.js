import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildM5CameraX}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.m5camera-x',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{KeyR:'reset'}};build(options={}){buildM5CameraX(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.m5camera-x.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildM5CameraX(h,options),options);}}
export{LegoClip,Wall1515}from'./accessories.js';export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
