import {printedArtwork} from '../../modeling/artwork.js';
const image=name=>new URL(`./artwork/reference-redraw-${name}.png`,import.meta.url).href;
export function addStickers(host){
 const panels=[];
 const add=(name,size,position,face='front',rotation=0,depth=.15)=>{for(const panel of printedArtwork(host,{target:host.parts['upper-housing'],url:image(name),size,position,face,rotation,depth,artworkKind:'reference-redraw',name:`StamPLC ${name} (reference redraw)`})??[]){panel.userData.source='reference-redraw';panels.push(panel);}};
 add('front-main',[67.5,15.1],[0,-16.9,10.3],'front',0,.5);
 add('front-inputs',[37,37*34/400],[14,36.4,10.2]);
 add('front-relays',[63,4.2],[0,-33.9,10.2]);
 add('front-note',[8.4,8.4*312/90],[-30.1,12.6,13.8]);
 // The current enclosure has no exterior support at the photographed side-label
 // height. Keep those labels deferred instead of creating a floating film.
 return panels;
}
