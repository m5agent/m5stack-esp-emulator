import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildMiniOled}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.mini-oled',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(){buildMiniOled(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.mini-oled.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,buildMiniOled,options);}}
export{spec};export default Model;
