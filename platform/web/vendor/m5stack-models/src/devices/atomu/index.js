/** MIT.Own K117 complete physical reconstruction and conservative visual API. */
import {Device} from '../../core/index.js';
import {buildAtomU} from './assembly.js';
import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export {spec,defaults,configurations,configurationSchema};
class AtomU extends Device{static meta={id:'m5stack.atomu',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'button'}};build(options={}){buildAtomU(this,options);}}
export const Model=AtomU;export default AtomU;
