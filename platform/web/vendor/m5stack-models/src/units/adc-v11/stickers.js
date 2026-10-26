import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){return[
 ...(printedArtwork(host,{target:host.adcV11Assembly.terminal.roof,url:front,size:[7.5,4.2],position:[0,8.8,6.2],depth:.12,artworkKind:'reference-redraw',name:'ADC v1.1 own-photo positive-negative terminal reference redraw'})??[]),
 ...(printedArtwork(host,{target:host.parts['ADC v1.1 complete native assembled shell'],url:back,size:[16,12.2],position:[0,7.6,-3.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'ADC v1.1 own-photo rear label reference redraw'})??[])
 ];}
