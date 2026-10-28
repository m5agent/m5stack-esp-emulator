import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){const result=[];for(const[face,url]of[['front',front],['back',back]]){const target=host.nbiotCnAssembly.films[face];if(target)result.push(...(printedArtwork(host,{target,url,size:spec.labels[face].size,position:spec.labels[face].printPosition,face,depth:.1,artworkKind:'reference-redraw',name:'NBIoT-CN exactown U112 '+face+' official-photo accurate code redraw'})??[]));}return result;}
