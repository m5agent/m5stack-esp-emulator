import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./education-cn-back.png',import.meta.url).href;
export function addStickers(host){
 if(host.options.stickerVariant!=='education-cn')return [];
 const panels=printedArtwork(host,{target:host.parts.housing,url:back,size:[16.1,12.1],position:[0,6.4,-3.8],face:'back',depth:.12,name:'Angle official Chinese education rear sticker'});
 for(const panel of panels??[])panel.userData.stickerVariant='education-cn';return panels;
}
