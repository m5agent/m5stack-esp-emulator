import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
const terminal=new URL('./reference-redraw-terminal.png',import.meta.url).href;
export function addStickers(host){
 const roof=host.powerSocket.children.find(o=>o.name==='8Servos power socket roof with four real inspection windows');
 return [printedArtwork(host,{target:host.parts['8Servos front shell'],url:front,size:[10.3,27],position:[-4.2,3,3.9],face:'front',depth:.5,artworkKind:'reference-redraw',name:'8Servos front channel print (reference redraw)'}),printedArtwork(host,{target:host.parts['8Servos rear shell'],url:back,size:[15.8,35],position:[0,6.95,-3.8],face:'back',depth:.1,artworkKind:'reference-redraw',name:'8Servos back schematic label (reference redraw)'}),printedArtwork(host,{target:roof,url:terminal,size:[15,3.2],position:[0,24.4,6.45],face:'front',depth:.12,artworkKind:'reference-redraw',name:'8Servos fixed terminal HV/G/G/5V print (reference redraw)'})];
}
