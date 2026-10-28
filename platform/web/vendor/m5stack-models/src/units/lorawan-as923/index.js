import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildLoRaWANAS923}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.lorawan-as923',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};build(options={}){buildLoRaWANAS923(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.lorawan-as923.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildLoRaWANAS923(h,options),options);}}
export{Antenna}from'./Antenna.js';export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
