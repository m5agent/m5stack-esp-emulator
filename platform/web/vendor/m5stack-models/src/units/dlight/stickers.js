import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Same-model rear label newly drawn from the official U136 reference. */
export function addStickers(host){return printedArtwork(host,{target:host.parts['DLight complete native assembled front and rear shell'],url:back,size:[16,12],position:[0,7,-3.8],face:'back',depth:.14,name:'DLight rear model and PORT.A pin-label reference redraw',artworkKind:'reference-redraw'})??[];}
