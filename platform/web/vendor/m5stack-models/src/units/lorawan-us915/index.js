import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildLoRaWANUS915}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.lorawan-us915',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};build(options={}){buildLoRaWANUS915(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.lorawan-us915.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildLoRaWANUS915(h,options),options);}}
export{Antenna}from'./Antenna.js';export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
