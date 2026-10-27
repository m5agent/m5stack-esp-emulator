import {printedArtwork} from '../../modeling/artwork.js';

const front=new URL('./reference-redraw-front-legends.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.body.getObjectByName('CardKB front solder mask'),url:front,size:[84,54],position:[0,0,-2.15],face:'front',depth:.12,artworkKind:'reference-redraw',name:'CardKB fixed PCB key legends (reference redraw)'});
}
