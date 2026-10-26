import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['Synth complete native assembled shell'];
 // The exact-product front photograph shows an actual narrow adhesive label
 // crossing central grille apertures. The fixed speaker remains behind them.
 const a=printedFilm(host,{url:front,size:[6.3,28.8],position:[0,9,8.012],face:'front',artworkKind:'reference-redraw',name:'Synth front adhesive label (reference redraw)'});
 const b=printedArtwork(host,{target,url:back,size:[16.4,29],position:[0,7.1,-7.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'Synth rear schematic sticker (reference redraw)'});
 return {front:a,back:b};
}
