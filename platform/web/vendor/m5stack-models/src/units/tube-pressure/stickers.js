import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Same-model label newly drawn from the official rear reference; no photograph crop. */
export function addStickers(host){return printedArtwork(host,{target:host.parts['Tube Pressure complete native rear shell'],url:back,size:[16,13],position:[0,6.5,-3.8],face:'back',depth:.14,name:'Tube Pressure back model and PORT.B pin-label reference redraw',artworkKind:'reference-redraw'})??[];}
