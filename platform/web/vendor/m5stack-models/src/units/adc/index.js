import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildADC}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.adc',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size};build(options={}){buildADC(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.adc.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildADC(h,options),options);}}
export{TerminalPlug}from'./TerminalPlug.js';export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Model;
