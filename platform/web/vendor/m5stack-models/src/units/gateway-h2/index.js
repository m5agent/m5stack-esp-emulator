import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildGatewayH2}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.gateway-h2',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){buildGatewayH2(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.gateway-h2.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildGatewayH2(h,options),options);}}
export{spec};export default Model;
