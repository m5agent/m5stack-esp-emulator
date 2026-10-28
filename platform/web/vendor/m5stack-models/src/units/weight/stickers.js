import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){const {films}=host.weightAssembly;return [...(printedArtwork(host,{target:films.front,url:front,size:spec.labels.front.size,position:[0,11.1,6.2],face:'front',depth:.1,name:'Weight exact U030 front A+/A-/E-/E+ official-reference redraw',artworkKind:'reference-redraw'})??[]),...(printedArtwork(host,{target:films.back,url:back,size:spec.labels.back.size,position:spec.labels.back.position,face:'back',depth:.1,name:'Weight exact U030 silver rear label official-reference redraw',artworkKind:'reference-redraw'})??[])];}
