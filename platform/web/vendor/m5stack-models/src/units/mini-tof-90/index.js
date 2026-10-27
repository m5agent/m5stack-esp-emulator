import {Device,Module}from'../../core/index.js';
import {buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import {buildMiniToF90}from'./assembly.js';
import {spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.mini-tof-90',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){buildMiniToF90(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.mini-tof-90.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildMiniToF90,options);}}
export{spec};export default Model;
