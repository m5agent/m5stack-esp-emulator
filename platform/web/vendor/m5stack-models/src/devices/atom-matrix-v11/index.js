/** MIT. Exact C008-B-V11 revision:own native source,25 external RGB pixels and physical input. */
import {Device} from '../../core/index.js';
import {buildAtomMatrixV11} from './assembly.js';
import {spec,defaults,configurations,configurationSchema} from './dimensions.js';
export {spec,defaults,configurations,configurationSchema};
class AtomMatrixV11 extends Device{static meta={id:'m5stack.atom-matrix-v11',name:spec.name,sku:spec.sku,revision:'v1.1',vendor:'M5Stack',size:spec.size,keymap:{Space:'button'}};build(options={}){buildAtomMatrixV11(this,options);}}
export const Model=AtomMatrixV11;export default AtomMatrixV11;
