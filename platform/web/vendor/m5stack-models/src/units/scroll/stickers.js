import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./education-cn-back.png',import.meta.url).href;
export function addStickers(host){
 if(host.options.stickerVariant!=='education-cn')return [];
 const panels=printedArtwork(host,{target:host.parts['Scroll back shell'],url:back,size:[19.8,13.8],position:[0,7,-3.8],face:'back',depth:.12,name:'Scroll official Chinese education rear sticker'});
 for(const panel of panels??[])panel.userData.stickerVariant='education-cn';return panels;
}
