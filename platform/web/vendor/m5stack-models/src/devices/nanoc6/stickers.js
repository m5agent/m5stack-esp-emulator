import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const image=name=>new URL(`./artwork/reference-redraw-${name}.png`,import.meta.url).href;
export function addStickers(host){
 const panels=[];
 const add=(name,options)=>{for(const panel of printedArtwork(host,{url:image(name),artworkKind:'reference-redraw',name:`NanoC6 ${name} (reference redraw)`,...options})??[]){panel.userData.source='reference-redraw';panels.push(panel);}};
 add('rear',{target:host.parts['rear-shell'],size:[8.6,8.6*150/88],position:[0,-.15,-4.55],face:'back',depth:.15});
 // Official side views show one rectangular adhesive sheet crossing the
 // assembled shell seam. Its footprint stays clear of the IR/RGB apertures.
 for(const [name,x,face]of [['ce',6.01,'right'],['weee',-6.01,'left']]){
  const panel=printedFilm(host,{url:image(name),size:[7.8,6],position:[x,-3,-1.45],face,artworkKind:'reference-redraw',name:`NanoC6 ${name} (reference redraw)`});
  if(panel){panel.userData.source='reference-redraw';panels.push(panel);}
 }
 return panels;
}
