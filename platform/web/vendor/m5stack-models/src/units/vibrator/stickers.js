import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-back.png',import.meta.url).href;
/** Exact U059 label text is DC MOTOR / N20 / OUT; reconstructed from official photo. */
export function addStickers(host){
 return printedArtwork(host,{target:host.parts['Vibrator complete native double shell'],url:back,size:[16,12],position:[0,7.1,-3.8],face:'back',depth:.14,name:'Vibrator reference-redrawn DC MOTOR rear label',artworkKind:'reference-redraw'})??[];
}
