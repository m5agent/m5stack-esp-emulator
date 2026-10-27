import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./source-vector-front.png',import.meta.url).href,back=new URL('./source-vector-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['DAC2 complete native assembled shell'];
 // Exact source contours, including the mounting-bore die cuts. Converter
 // compound glyph fill semantics restored before high-resolution rasterization.
 return[...(printedArtwork(host,{target,url:front,size:[16,13.8996],position:[0,-1.75,3.8],depth:.12,artworkKind:'source-vector-raster',name:'DAC2 source-vector front terminal/title/Grove label'})??[]),...(printedArtwork(host,{target,url:back,size:[16,12],position:[0,7.45,-3.8],face:'back',depth:.12,artworkKind:'source-vector-raster',name:'DAC2 source-vector rear GP8413/I2C label'})??[])];
}
