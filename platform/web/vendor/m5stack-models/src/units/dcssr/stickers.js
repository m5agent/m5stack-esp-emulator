import {printedArtwork} from '../../modeling/artwork.js';
const rear=new URL('./reference-redraw-controller-back.png',import.meta.url).href,ssr=new URL('./reference-redraw-ssr.png',import.meta.url).href;
export function addStickers(host,{native,panel}){
 return[...(printedArtwork(host,{target:native,url:rear,size:[41.4,15.6],position:[0,-30.63036,4],face:'back',depth:.18,artworkKind:'reference-redraw',name:'DCSSR controller rear exact-U140 label redraw'})??[]),...(printedArtwork(host,{target:panel,url:ssr,size:[43,29],position:[0,9.4,13.4],depth:.2,artworkKind:'reference-redraw',name:'DCSSR DELIXI SSR nameplate exact-U140 photo redraw'})??[])];
}
