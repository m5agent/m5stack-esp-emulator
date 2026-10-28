/** MIT. Exact EU868 source verified independently;shared official shell blob permits common construction methods. */
import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildLoRaWANEU868}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.lorawan-eu868',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};build(options={}){buildLoRaWANEU868(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.lorawan-eu868.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildLoRaWANEU868(h,options),options);}}
export{Antenna}from'./Antenna.js';export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
