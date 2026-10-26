import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildMq} from './assembly.js';
import {MQ5Cartridge} from './MQ5Cartridge.js';
import {spec} from './dimensions.js';
function attachCartridge(host,options){if(options.mq5Cartridge!==false)host.port('mq5').attach(new MQ5Cartridge({artwork:options.artwork}));}
export class Model extends Device{
 static meta={id:'m5stack.unit.mq',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){buildMq(this);attachCartridge(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.mq.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildMq,options);attachCartridge(this,options);}
}
export {MQ5Cartridge,spec};
export default Model;
