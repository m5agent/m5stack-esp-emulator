import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildNeoHex}from'./assembly.js';
import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.neohex',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,geometrySource:spec.geometrySource};build(options={}){buildNeoHex(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.neohex.grove',name:spec.name,sku:spec.sku,connector:'grove',inputPort:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildNeoHex(h,options),options);}}
export{Diffuser}from'./Diffuser.js';export{spec};export default Model;
