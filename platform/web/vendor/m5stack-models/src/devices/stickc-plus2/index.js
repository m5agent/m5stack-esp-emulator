/** MIT. M5StickC Plus2 (K016-P2), original exact-model photo/drawing reconstruction. */
import {Device,Display} from '../../core/index.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {buildConstruction} from './construction.js';
import {DIM,spec,defaults,configurations,configurationSchema,HAT_PINS,GROVE_PINS} from './dimensions.js';
export {DIM,spec,defaults,configurations,configurationSchema,HAT_PINS,GROVE_PINS};
export class StickCPlus2 extends Device {
 static meta={id:'m5stack.stickc-plus2',name:'M5StickC Plus2',sku:'K016-P2',vendor:'M5Stack',size:DIM.body,keymap:{Space:'a',Enter:'a',KeyA:'a',KeyB:'b',KeyP:'power',KeyC:'power'}};
 build({pixelEffect=true}={}){
  const a=buildConstruction(this),d=DIM.display;
  this.add(new Display({id:'lcd',label:'1.14-inch 135×240 TFT · ST7789V2',width:d.width,height:d.height,size:d.active,position:d.position,touch:false,pixelEffect,glass:{size:d.window,intensity:.12,roughness:.16},meta:{role:'external-framebuffer',driver:'ST7789V2',activeAreaSource:'Approximate own front-photo aperture aspect with nominal 1.14-inch diagonal; not the StickS3 A183 active area'}}));
  printedArtwork(this,{target:a.carrier,url:new URL('./artwork/rear-reference-redraw.png',import.meta.url).href,size:DIM.label.size,position:DIM.label.position,face:'back',depth:.15,artworkKind:'reference-redraw',name:'Plus2 rear pin/spec label · own-photo reference redraw'});
 }
}
export const Model=StickCPlus2;
export default Model;
