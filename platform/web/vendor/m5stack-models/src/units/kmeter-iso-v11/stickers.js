import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./official-front.png',import.meta.url).href,back=new URL('./official-back.png',import.meta.url).href,connector=new URL('./reference-redraw-connector.png',import.meta.url).href;
export function addStickers(host){return[
 printedArtwork(host,{target:host.parts['front-shell'],url:front,size:[20.8,23.5],position:[0,1.75,3.8],face:'front',depth:.12,artworkKind:'official-vector-raster',name:'KMeter-ISO exact v1.1 front source artwork raster'}),
 printedArtwork(host,{target:host.parts['rear-shell'],url:back,size:[16,35],position:[0,7.25,-3.8],face:'back',depth:.12,artworkKind:'official-vector-raster',name:'KMeter-ISO exact v1.1 rear source artwork raster'}),
 printedArtwork(host,{target:host.kmeterIsoAssembly.thermocouple.body,url:connector,size:[16.2,9.9],position:[0,20.6,3.8],face:'front',depth:.12,artworkKind:'reference-redraw',name:'KMeter-ISO K connector printed marks reference redraw'})
 ];}
