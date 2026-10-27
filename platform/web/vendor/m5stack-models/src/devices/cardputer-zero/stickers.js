import {printedArtwork} from '../../modeling/artwork.js';

// Front-view +X is the HDMI/audio/Grove side (official gallery 04/06).
// Raster dimensions preserve the original PNG aspect. Top image U=-X, V=+Z.
export function addPerimeterStickers(host){
 const surface=name=>host.body.getObjectByName(name);
 const add=(file,options)=>printedArtwork(host,{url:new URL(`./artwork/${file}.png`,import.meta.url).href,...options});
 add('right-display-audio-grove',{target:surface('right lower shell'),size:[35,35*42/413],position:[42,-5.8,-4.8],face:'right',name:'CardputerZero official right display audio and Grove sticker'});
 add('left-usb-network',{target:surface('left lower shell'),size:[25,25*110/295],position:[-42,7.3,-3.65],face:'left',name:'CardputerZero official fixed USB network and Boot callout sticker'});
 // One projector gives both real shell meshes identical UV across the split.
 // The lower printed edge clears the EXT aperture at Z=4.3 mm.
 add('top-gpio',{target:[surface('Upper white lid edge'),surface('Upper expansion shell')],size:[18.5,18.5*51/216],position:[0,27,6.55],face:'top',rotation:Math.PI,name:'CardputerZero official top GPIO sticker'});
 add('top-sd',{target:surface('Upper expansion shell'),size:[14.1,14.1*72/172],position:[-18.1,27,1.75],face:'top',rotation:Math.PI,name:'CardputerZero official microSD sticker'});
}
