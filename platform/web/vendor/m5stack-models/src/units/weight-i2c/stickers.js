import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['Weight-I2C assembled housing'];
 // Project only existing native shell triangles; the transparent T-shaped print
 // does not span the open terminal/Grove or mounting bores.
 return [printedArtwork(host,{target,url:front,size:[16.4,15.2],position:[0,-1.6,4],face:'front',depth:.1,artworkKind:'reference-redraw',name:'Weight-I2C front terminal/title/pin print (reference redraw)'}),printedArtwork(host,{target,url:back,size:[16,11.4],position:[0,7.3,-3.8],face:'back',depth:.1,artworkKind:'reference-redraw',name:'Weight-I2C back label (reference redraw)'})];
}
