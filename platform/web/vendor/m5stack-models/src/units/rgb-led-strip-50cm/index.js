/** MIT; exact A093500mm/30pixel independently authored visual assembly. */
import {Device,Module} from '../../core/index.js';
import {buildStrip} from './assembly.js';
import {spec} from './dimensions.js';
export {defaults,configurationSchema,configurations,spec} from './dimensions.js';
export {InputAdapter} from './Adapter.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.rgb-led-strip-50cm',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:null,nominalStripMm:[500,10],keymap:{}};
 build(options={}){buildStrip(this,options,false);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.rgb-led-strip-50cm.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildStrip(this,options,true);}
}
export default Model;
