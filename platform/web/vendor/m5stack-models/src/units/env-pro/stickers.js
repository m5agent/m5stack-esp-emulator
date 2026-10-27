import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.parts['ENV Pro complete native double shell'],url:back,size:[16,12],position:[0,7,-3.8],face:'back',depth:.15,name:'ENV Pro official rear BME688 label'});
}
