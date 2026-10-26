import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const image=name=>new URL(`./artwork/reference-redraw-${name}.png`,import.meta.url).href;
export function addStickers(host){
 const panels=[];
 const add=(name,options)=>{for(const panel of printedArtwork(host,{url:image(name),artworkKind:'reference-redraw',name:`Arduino Nesso N1 ${name} (reference redraw)`,...options})??[]){panel.userData.source='reference-redraw';panels.push(panel);}};
 // The official rear photo shows a continuous factory adhesive sheet spanning
 // the molded recesses. It ends above the two rear fasteners and USB opening.
 const rear=printedFilm(host,{parent:host.parts['back-cover'],url:image('rear'),size:[20.1,20.1*430/216],position:[0,1.8,-11.015],face:'back',artworkKind:'reference-redraw',name:'Arduino Nesso N1 rear (reference redraw)'});
 if(rear){rear.userData.source='reference-redraw';panels.push(rear);}
 // Both visible factory labels span their shallow molded recesses. The top
 // film keeps a physical cutout around the measured native IR opening.
 const top=printedFilm(host,{parent:host.parts['upper-housing'],url:image('top'),size:[16,16*94/170],position:[0,24.015,4.4],face:'top',rotation:Math.PI,holes:[{w:2.4,h:1.9,r:.15,cx:6.75,cy:.65}],artworkKind:'reference-redraw',name:'Arduino Nesso N1 top (reference redraw)'});
 const qwiic=printedFilm(host,{parent:host.parts['upper-housing'],url:image('qwiic'),size:[10.5,3.5],position:[-12.015,0,2],face:'left',artworkKind:'reference-redraw',name:'Arduino Nesso N1 qwiic (reference redraw)'});
 for(const panel of [top,qwiic])if(panel){panel.userData.source='reference-redraw';panels.push(panel);}
 // The antenna label belongs to the antenna's connector-side surface, which is
 // hidden in its current storage pose. It is never printed on the outer back cover.
 add('antenna',{target:host.parts['stowed-lora-antenna'],size:[8.2,8.2*190/84],position:[-.05,-1.2,-5],face:'front',depth:.15});
 return panels;
}
