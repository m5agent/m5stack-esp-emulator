/** MIT; own original U017 complete appearance,not U038/F. */
import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildM5Camera}from'./assembly.js';import{spec}from'./dimensions.js';
export const defaults={};export const configurationSchema={artwork:{type:'boolean',default:true,meaning:'Rear ink only;retain physical label substrate,case/ears,PCB/WROVERshield and complete support'}};export const configurations=[{id:'complete',name:'完整原版 M5Camera U017',options:{}}];
export class Model extends Device{static meta={id:'m5stack.unit.m5camera',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{KeyR:'reset'}};build(){buildM5Camera(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.m5camera.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildM5Camera(h),options);}}
export{spec};export default Model;
