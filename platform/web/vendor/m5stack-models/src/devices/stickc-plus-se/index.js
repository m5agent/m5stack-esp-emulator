/** MIT. M5StickC Plus SE (K016-P-SE), original exact-model photo/drawing reconstruction. */
import {Device,Display} from '../../core/index.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {buildConstruction} from './construction.js';
import {DIM,spec,defaults,configurations,configurationSchema,HAT_PINS,GROVE_PINS} from './dimensions.js';
export {DIM,spec,defaults,configurations,configurationSchema,HAT_PINS,GROVE_PINS};
export class StickCPlusSE extends Device {
 static meta={id:'m5stack.stickc-plus-se',name:'M5StickC Plus SE',sku:'K016-P-SE',vendor:'M5Stack',size:DIM.body,keymap:{Space:'a',Enter:'a',KeyA:'a',KeyB:'b',KeyP:'power',KeyC:'power'}};
 build({pixelEffect=true}={}){
  const a=buildConstruction(this),d=DIM.display;
  this.add(new Display({id:'lcd',label:'1.14-inch 135×240 TFT · ST7789V2',width:d.width,height:d.height,size:d.active,position:d.position,touch:false,pixelEffect,glass:{size:d.window,intensity:.12,roughness:.16},meta:{role:'external-framebuffer',driver:'ST7789V2',activeAreaSource:'Own SE mechanical drawing14.8x24.86mm; hidden optical stack remains inferred'}}));
  printedArtwork(this,{target:a.carrier,url:new URL('./artwork/rear.png',import.meta.url).href,size:DIM.label.size,position:DIM.label.position,face:'back',depth:.15,artworkKind:'official-raster',name:'Plus SE rear pin/spec label · approved ordinary raster; no source file distributed'});
 }
}
export const Model=StickCPlusSE;
export default Model;
