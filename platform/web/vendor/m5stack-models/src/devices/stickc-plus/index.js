/** MIT. M5StickC Plus (K016-P) own native source and exact-model reconstruction. */
import {Device,Display} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {spec,DIM} from './dimensions.js';
export {spec,DIM,defaults,configurations,configurationSchema,HAT_PINS,GROVE_PINS} from './dimensions.js';
export class StickCPlus extends Device{
 static meta={id:'m5stack.stickc-plus',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.nominalMm,keymap:{Space:'a',KeyA:'a',KeyB:'b',KeyP:'power'}};
 build({pixelEffect=true}={}){const a=buildAssembly(this),d=DIM.display;this.add(new Display({id:'lcd',label:spec.pixels.join('×')+' non-touch TFT',width:spec.pixels[0],height:spec.pixels[1],size:d.active,position:d.position,touch:false,pixelEffect,glass:{intensity:.12,roughness:.16},meta:{role:'external-framebuffer',driver:spec.driver,activeAreaSource:'Own photo aperture with nominal diagonal;visual inference'}}));printedArtwork(this,{target:a.label,url:new URL('./artwork/rear-reference-redraw.png',import.meta.url).href,size:[21,37],position:[0,4.5,-7.065],face:'back',depth:.15,name:spec.name+' own rear label reference redraw',artworkKind:'reference-redraw'});}
}
export const Model=StickCPlus;export default Model;
