import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./source-vector-front.png',import.meta.url).href,back=new URL('./source-vector-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['NFC U216 complete native assembled shell'];
 // Exact U216 source contours/fills; converter compound glyph winding recovered
 // before high-resolution rasterization. No photo pixels or original vector shipped.
 return [...(printedArtwork(host,{target,url:front,size:[17.7,27.7],position:[0,6.5,3.8],depth:.14,artworkKind:'source-vector-raster',name:'NFC U216 source-vector blue front label'})??[]),...(printedArtwork(host,{target,url:back,size:[15.9,27.9],position:[0,6.5,-3.8],face:'back',depth:.14,artworkKind:'source-vector-raster',name:'NFC U216 source-vector ST25R3916 I2C rear label'})??[])];
}
