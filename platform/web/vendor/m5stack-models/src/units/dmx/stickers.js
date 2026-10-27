import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 return[...(printedArtwork(host,{target:host.parts['DMX native front shell and XLR cradle'],url:front,size:[16,8.3],position:[2.2,-3.62,3.8],depth:.16,artworkKind:'reference-redraw',name:'DMX fixed front switch/name label (official-photo redraw)'})??[]),...(printedArtwork(host,{target:host.parts['DMX native rear shell'],url:back,size:[17.8,28.3],position:[0,7.15,-3.8],face:'back',depth:.16,artworkKind:'reference-redraw',name:'DMX rear isolation diagram (official-photo redraw)'})??[])];
}
