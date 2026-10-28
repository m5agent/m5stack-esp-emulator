/** MIT. Exact original U121-B complete own-parametric appearance. */
import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildPoECAMWOriginal} from './assembly.js';
import {spec} from './dimensions.js';
export const defaults={};
export const configurationSchema={artwork:{type:'boolean',default:true,meaning:'Rear ink only;retain physical die-cut film,original shell,PCB/PoE/lens/contact supports and uncoloured M5'}};
export const configurations=[{id:'complete',name:'完整原版 PoE CAM-W U121-B',options:{}}];
export class Model extends Device{static meta={id:'m5stack.unit.poe-cam-w',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'user',KeyR:'reset'}};build(){buildPoECAMWOriginal(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.poe-cam-w.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){buildGroveModuleAssembly(this,h=>buildPoECAMWOriginal(h),options);}}
export {spec};export default Model;
