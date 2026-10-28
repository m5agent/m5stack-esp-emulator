/** MIT; original MEGA328P U035,not ATMega8A U035-B. */
import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildCardKB} from './assembly.js';
import {spec,KEYMAP} from './dimensions.js';
export {spec,KEYS,KEYMAP,defaults,configurationSchema,configurations} from './dimensions.js';
export class Model extends Device{static meta={id:'m5stack.unit.cardkb-original',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,nominalStatus:spec.nominalStatus,photoCaptionMm:spec.photoCaptionMm,keymap:KEYMAP};build(){buildCardKB(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.cardkb-original.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){const {unitFrame}=buildGroveModuleAssembly(this,buildCardKB,options);if(!options.unitPose){unitFrame.setPose({rotation:[0,0,Math.PI/2]});unitFrame.setDistance(options.cableLength??35);}}}
export default Model;
