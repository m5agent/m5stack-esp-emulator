import {Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildTimerPwr}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.timerpwr',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:spec.keymap};build(){buildTimerPwr(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.timerpwr.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:spec.keymap};build(options={}){buildGroveModuleAssembly(this,buildTimerPwr,options);}}
export{spec};export default Model;
