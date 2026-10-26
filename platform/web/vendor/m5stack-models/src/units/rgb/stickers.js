import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.parts.housing,url:back,size:[16,12],position:[0,6.4,-3.8],face:'back',depth:.12,name:'RGB LED official rear sticker'});
}
