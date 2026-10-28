import{Device,Module}from'../../core/index.js';
import{buildGroveModuleAssembly}from'../../modeling/grove-cable.js';
import{buildNeco}from'./assembly.js';
import{spec}from'./dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.neco',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,geometrySource:spec.geometrySource,keymap:{Space:'button'}};
 build(){buildNeco(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.neco.grove',name:spec.name,sku:spec.sku,connector:'grove',inputPort:'grove'};
 build(options={}){buildGroveModuleAssembly(this,h=>buildNeco(h),options);}
}
export{spec};export default Model;
