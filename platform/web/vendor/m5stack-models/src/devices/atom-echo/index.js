/** MIT.Independent exact-product host;mechanical/visual only. */
import {Device} from "../../core/index.js";
import {buildAtomEcho} from "./assembly.js";
import {spec,defaults,configurations,configurationSchema} from "./dimensions.js";
export {spec,defaults,configurations,configurationSchema};
class AtomEcho extends Device{static meta={id:"m5stack.atom-echo",name:spec.name,sku:spec.sku,vendor:"M5Stack",size:spec.size,keymap:{Space:"button"}};build(options={}){buildAtomEcho(this,options);}}
export const Model=AtomEcho;export default AtomEcho;
