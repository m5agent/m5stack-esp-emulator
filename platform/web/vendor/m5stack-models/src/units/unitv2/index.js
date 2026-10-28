import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildUnitV2}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.unitv2',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{Space:'user'}};build(){buildUnitV2(this,this.options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.unitv2.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{Space:'user'}};build(options={}){buildGroveModuleAssembly(this,host=>buildUnitV2(host,options),options);}}
export{MicroSdCard,UsbCable,Stand,BackBrick}from'./accessories.js';export{spec};export default Model;
