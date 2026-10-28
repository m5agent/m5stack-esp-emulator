/** MIT; exact bare original U082 appearance,not F/X. */
import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildTimerCamera}from'./assembly.js';import{spec}from'./dimensions.js';
export const defaults={};export const configurationSchema={artwork:{type:'boolean',default:true,meaning:'PCB ink only;retain both populated board faces and optics,no adhesive film exists'}};export const configurations=[{id:'bare',name:'裸板 TimerCamera U082',options:{}}];
export class Model extends Device{static meta={id:'m5stack.unit.timercamera',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{KeyR:'reset',KeyP:'power'}};build(){buildTimerCamera(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.timercamera.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildTimerCamera(h),options);}}
export{spec};export default Model;
