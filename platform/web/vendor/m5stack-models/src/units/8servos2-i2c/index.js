import{Device,Module}from'../../core/index.js';import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';import{buildEightServos2I2C}from'./assembly.js';import{spec}from'./dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.8servos2-i2c',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};build(options={}){buildEightServos2I2C(this,options);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.8servos2-i2c.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildEightServos2I2C(h,options),options);}}
export{spec};export default Model;
