import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildLoRaE220920}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.lora-e220-920',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Digit1:'mode-0',Digit2:'mode-1'}};build(options={}){buildLoRaE220920(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.lora-e220-920.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{Digit1:'mode-0',Digit2:'mode-1'}};build(options={}){buildGroveModuleAssembly(this,buildLoRaE220920,options);}}
export{Antenna}from'./Antenna.js';export{spec}from'./dimensions.js';export default Model;
