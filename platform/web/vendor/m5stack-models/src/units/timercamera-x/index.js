import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildTimerCameraX}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.timercamera-x',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildTimerCameraX(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.timercamera-x.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildTimerCameraX(h,options),options);}}
export{TwoEarMount,TwinHoleMount}from'./accessories.js';export{spec};export default Model;
