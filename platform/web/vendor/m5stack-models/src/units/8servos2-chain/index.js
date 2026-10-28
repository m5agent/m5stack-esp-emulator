import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildEightServosChain} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.8servos2-chain',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};
 build(){buildEightServosChain(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.8servos2-chain.grove',name:spec.name+' · Chain IN cable',sku:spec.sku,connector:'grove',inputPort:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildEightServosChain,options);}
}
export {spec};export default Model;
