import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildPoeP4}from'./assembly.js';
import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.poe-p4',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'user'}};build(){buildPoeP4(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.poe-p4.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{Space:'user'}};build(options={}){buildGroveModuleAssembly(this,buildPoeP4,options);}}
export{spec};export default Model;
