import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
import {CHANNELS} from './dimensions.js';

const rear=new URL('./reference-redraw-back.png',import.meta.url).href;
const legends=Array.from({length:8},(_,i)=>new URL(`./reference-redraw-ch${i+1}.png`,import.meta.url).href);
const sw=new URL('./reference-redraw-sw.png',import.meta.url).href;
const switch0=new URL('./reference-redraw-switch-0.png',import.meta.url).href;
const switch1=new URL('./reference-redraw-switch-1.png',import.meta.url).href;
export function addStickers(host){
 const panels=[];
 const add=(options)=>panels.push(...(printedArtwork(host,{artworkKind:'reference-redraw',...options})??[]));
 // The photographed adhesive label spans the CAD's rear service window.
 const rearFilm=printedFilm(host,{parent:host.parts['8Encoder back shell'],url:rear,size:[19.4,29.5801980198],position:[0,-31,-4.825],face:'back',artworkKind:'reference-redraw',name:'8Encoder rear pin-table label (reference redraw)'});if(rearFilm)panels.push(rearFilm);
 for(const item of CHANNELS)add({target:host.parts['8Encoder front shell'],url:legends[item.number-1],size:[3.6,1.2],position:[6.8,item.y,5],face:'front',rotation:Math.PI/2,depth:.12,name:`8Encoder fixed CH${item.number} legend (reference redraw)`});
 add({target:host.parts['8Encoder front shell'],url:sw,size:[3.6,1.2],position:[6.8,59,5],face:'front',rotation:Math.PI/2,depth:.12,name:'8Encoder fixed SW legend (reference redraw)'});
 for(const [label,url,x]of [['1',switch1,-1.45],['0',switch0,1.45]])add({target:host.parts['8Encoder front shell'],url,size:[1.2,.9],position:[x,56.6,5],face:'front',rotation:Math.PI/2,depth:.12,name:`8Encoder fixed switch ${label} legend (reference redraw)`});
 return panels;
}
