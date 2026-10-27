import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back-vector.png',import.meta.url).href;
const fingerprint=new URL('./official-fingerprint-native.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['Fingerprint2 native back shell'],panels=[];
 panels.push(...(printedArtwork(host,{target,url:back,size:[21,22.5],position:[0,7.1,-3.8],face:'back',depth:.16,name:'Fingerprint2 official rear vector-derived label'})??[]));
 // The original fingerprint symbol is an embedded 200×200 bitmap. Keep its
 // native pixel grid as a separate final raster, aligned by the source layout.
 const icon=printedArtwork(host,{target,url:fingerprint,size:[10.019,10.019],position:[.168,8.886,-3.8],face:'back',depth:.16,name:'Fingerprint2 official native-resolution fingerprint symbol'})??[];
 for(const panel of icon)panel.position.z-=.003;
 panels.push(...icon);return panels;
}
