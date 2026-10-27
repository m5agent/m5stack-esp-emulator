import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./source-vector-back.png',import.meta.url).href,title=new URL('./reference-redraw-title.png',import.meta.url).href,blank=new URL('./reference-redraw-blank.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['MQ complete native assembled shell'];
 return[...(printedArtwork(host,{target,url:back,size:[16.05625,26.03125],position:[0,-2.4,-3.8],face:'back',depth:.2,artworkKind:'source-vector-raster',name:'MQ exact source-vector rear schematic and Grove label'})??[]),...(printedArtwork(host,{target,url:title,size:[16,4.8],position:[0,-12.5,3.8],depth:.16,artworkKind:'reference-redraw',name:'MQ own product Unit MQ front title'})??[]),...(printedArtwork(host,{target,url:blank,size:[13,7.3],position:[0,24.7,20.5],depth:2,artworkKind:'reference-redraw',name:'MQ own product blank identification sticker on curved hood'})??[])];
}
