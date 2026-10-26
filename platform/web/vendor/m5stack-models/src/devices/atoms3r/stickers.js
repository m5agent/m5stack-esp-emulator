import {printedArtwork,printedFilm} from '../../modeling/artwork.js';

// Rear registration follows the mounting axis and the 2.54 mm socket rows.
// Preserve each supplied raster's aspect ratio; concealed support geometry
// remains an appearance estimate rather than a manufacturing drawing.
export const REAR_LABEL_CENTER_Y=2.816896462184838;

export function addStickers(host,retainingPlate){
 const {parts}=host;
 // Both the official raster and the assembled rear photographs show this
 // yellow M2 area unpierced. The adhesive film covers the blind recess while
 // leaving the underlying mounting geometry and all nine socket bores intact.
 printedFilm(host,{url:new URL('./artwork/rear-main.png',import.meta.url).href,size:[12.075332348596751,15],position:[-.000771542531683356,REAR_LABEL_CENTER_Y,-6.475],face:'back',parent:retainingPlate,name:'Official AtomS3R rear pinout adhesive film'});
 // The certification label is on the fixed +Y edge and crosses the shell
 // split. Its native recessed land is Y11.8, beside the Y12 outer lip; the
 // projection volume includes both real surfaces and retains the IR notch.
 printedArtwork(host,{target:[parts['rear-shell'],parts['front-shell']],url:new URL('./artwork/certification.png',import.meta.url).href,size:[14.4,9.390327613104525],position:[-1.3,12.025,-.25],face:'top',depth:.6,name:'Official AtomS3R certification print'});
}
