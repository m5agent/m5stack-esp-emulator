import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildZigBee}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.zigbee',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){buildZigBee(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.zigbee.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildZigBee(h,options),options);}}
export{Antenna}from'./Antenna.js';export{spec};export default Model;
