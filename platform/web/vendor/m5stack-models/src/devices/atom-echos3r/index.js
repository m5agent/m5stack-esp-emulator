/** MIT.Independent exact-product host;mechanical/visual only. */
import {Device} from "../../core/index.js";
import {buildAtomEchoS3R} from "./assembly.js";
import {spec,defaults,configurations,configurationSchema} from "./dimensions.js";
export {spec,defaults,configurations,configurationSchema};
class AtomEchoS3R extends Device{static meta={id:"m5stack.atom-echos3r",name:spec.name,sku:spec.sku,vendor:"M5Stack",size:spec.size,keymap:{Space:"button"}};build(options={}){buildAtomEchoS3R(this,options);}}
export const Model=AtomEchoS3R;export default AtomEchoS3R;
