import {printedArtwork} from '../../modeling/artwork.js';
const standard=new URL('./source-vector-back.png',import.meta.url).href;
const education=new URL('./education-cn-back.png',import.meta.url).href;
/** Exact supplied U019 glyph contours; paint/visible layers restored from matching references. */
export function addStickers(host,target){
 const variant=host.options.stickerVariant??'standard';
 if(!['standard','education-cn'].includes(variant))return [];
 const panels=printedArtwork(host,{target,url:variant==='education-cn'?education:standard,size:[16,12],position:[0,-8.15,-4],face:'back',depth:.18,name:`Earth supplied-vector ${variant} rear label with restored reference paint`,artworkKind:'source-vector-raster'})??[];
 for(const p of panels)p.userData.stickerVariant=variant;
 return panels;
}
