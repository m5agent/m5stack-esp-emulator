import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildCatMGNSS}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.catm-gnss',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildCatMGNSS(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.catm-gnss.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildCatMGNSS(h,options),options);}}
export{LTEAntenna,GNSSAntenna}from'./Antenna.js';export{spec};export default Model;
