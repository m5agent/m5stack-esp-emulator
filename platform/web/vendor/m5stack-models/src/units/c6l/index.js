import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildC6l}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.c6l',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'user',KeyR:'reset'}};build(options={}){buildC6l(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.c6l.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{Space:'user',KeyR:'reset'}};build(options={}){buildGroveModuleAssembly(this,host=>buildC6l(host,options),options);}}
export{LoraAntenna,WifiAntenna}from'./Antennas.js';export{spec}from'./dimensions.js';export default Model;
