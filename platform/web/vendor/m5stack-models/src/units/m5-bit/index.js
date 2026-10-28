/** MIT; UnitM5BitA051 appearance/actualconnectors only. */
import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildM5Bit}from'./assembly.js';import{spec}from'./dimensions.js';
export const defaults={};export const configurationSchema={artwork:{type:'boolean',default:true,meaning:'Only ownPCB ink;allphysicalboard/packages/contacts retained'}};export const configurations=[{id:'complete',name:'完整原版 M5Bit 转接板',options:{}}];
export class Model extends Device{static meta={id:'m5stack.unit.m5-bit',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){buildM5Bit(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.m5-bit.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildM5Bit,options);}}
export{spec};export default Model;
