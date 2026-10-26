import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 return[...(printedArtwork(host,{target:host.parts['CAN native front shell'],url:front,size:[15.8,26.7],position:[0,2.3,3.8],depth:.16,artworkKind:'reference-redraw',name:'CAN front isolated-bus label (official-photo redraw)'})??[]),...(printedArtwork(host,{target:host.parts['CAN native rear shell'],url:back,size:[16,36],position:[0,7,-3.8],face:'back',depth:.16,artworkKind:'reference-redraw',name:'CAN rear isolation diagram (official-photo redraw)'})??[])];
}
