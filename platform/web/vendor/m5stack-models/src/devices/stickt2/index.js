/** MIT. K016-T2 own source thermal-imager visual host. */
import {Device,Display}from '../../core/index.js';import{buildAssembly}from './assembly.js';import{spec,DIM}from './dimensions.js';
export{spec,DIM,defaults,configurations,configurationSchema,GROVE_PINS}from './dimensions.js';
export class StickT2 extends Device{static meta={id:'m5stack.stickt2',name:'M5StickT2',sku:'K016-T2',vendor:'M5Stack',size:spec.nominalMm,keymap:{Space:'a',KeyA:'a',KeyB:'b',KeyP:'power',Enter:'press'}};build({pixelEffect=true}={}){buildAssembly(this);this.add(new Display({id:'lcd',label:'1.14-inch 135×240 ST7789 TFT',width:135,height:240,size:DIM.display.active,position:DIM.display.position,touch:false,pixelEffect,glass:{intensity:.1,roughness:.18},meta:{role:'external-framebuffer',driver:'ST7789',scope:'External pixels only;no thermal acquisition,color-map or temperature generation'}}));}}
export const Model=StickT2;export default Model;
