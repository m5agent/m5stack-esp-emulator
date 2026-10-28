import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildTimerCameraF}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.timercamera-f',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildTimerCameraF(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.timercamera-f.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildTimerCameraF(h,options),options);}}
export{Clip,Wall1515}from'./accessories.js';export{spec};export default Model;
