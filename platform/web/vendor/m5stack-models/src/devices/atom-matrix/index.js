/** MIT. Original C008-B host controller appearance and input/output intent only. */
import {Device} from '../../core/index.js';
import {buildAtomMatrix} from './assembly.js';
import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export {spec,defaults,configurations,configurationSchema};
class AtomMatrix extends Device{static meta={id:'m5stack.atom-matrix',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'button'}};build(options={}){buildAtomMatrix(this,options);}}
export const Model=AtomMatrix;
export default AtomMatrix;
