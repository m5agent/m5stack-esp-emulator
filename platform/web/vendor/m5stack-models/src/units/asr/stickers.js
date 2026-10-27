import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['ASR complete native assembled shell'];
 // The exact U194 front adhesive label bridges native centre grille apertures.
 // The physical fixed speaker remains behind every opening without artwork.
 const a=printedFilm(host,{url:front,size:[6.3,28.8],position:[0,9,8.012],face:'front',artworkKind:'reference-redraw',name:'ASR front adhesive label exact-U194 reference redraw'});
 const b=printedArtwork(host,{target,url:back,size:[16.4,29],position:[0,7.1,-7.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'ASR rear schematic sticker exact-U194 reference redraw'});
 return{front:a,back:b};
}
