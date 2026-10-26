import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const relayUrls=[1,2,3,4].map(i=>new URL(`./reference-redraw-relay-${i}.png`,import.meta.url).href);
export function addStickers(host){
 const panels=[];
 for(const[i,target]of host.fourRelayAssembly.relays.entries())panels.push(...(printedArtwork(host,{target,url:relayUrls[i],size:[18.1,9.6],position:[target.position.x,target.position.y,14.4],depth:.14,artworkKind:'reference-redraw',name:`4Relay channel ${i+1} label (official-photo redraw)`})??[]));
 panels.push(...(printedArtwork(host,{target:host.parts['4Relay native assembled shell pair'],url:front,size:[20,8],position:[0,-35.8,3.8],depth:.14,artworkKind:'reference-redraw',name:'4Relay fixed front name label (official-photo redraw)'})??[]));return panels;
}
