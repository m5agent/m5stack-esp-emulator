// MIT. Only cleaned supplied flat raster images; their rights remain with M5Stack.
import {printedFilm} from '../../modeling/artwork.js';
import {FACE,materials,plate} from './geometry.js';
export function addStickers(host){
 const backSize=[12,15],backPosition=[-.001830943,2.797851562,-4.56857],hole=[-.0018309429356115903,-2.7978515625],holes=[{radius:1.13,x:hole[0],y:hole[1]}];
 const carrier=plate(host.body,...backSize,.04,backPosition,materials.plastic(0xd8dad5,{roughness:.83}),'C124 real bored rear adhesive substrate',{radius:.03,holes});carrier.quaternion.copy(FACE.back);carrier.userData.visualFamily='label-substrate';
 const back=printedFilm(host,{url:new URL('./artwork/bottom.png',import.meta.url).href,size:backSize,position:[...backPosition.slice(0,2),backPosition[2]-.046],face:'back',holes:[{w:2.26,h:2.26,r:1.13,cx:hole[0],cy:hole[1]}],name:'C124 supplied bottom ink on actual bored substrate',artworkKind:'official-raster'});
 // Entire ordinary image aspect is retained, inside the native +Y recessed land.
 const complianceSize=[13.5,13.5*146/402],centre=[.9,11.808,-.05],side=plate(host.body,...complianceSize,.028,centre,materials.plastic(0xd8dad5,{roughness:.84}),'C124 real conformity adhesive substrate',{radius:.025});side.quaternion.copy(FACE.top);side.userData.visualFamily='label-substrate';
 const certification=printedFilm(host,{url:new URL('./artwork/compliance.png',import.meta.url).href,size:complianceSize,position:[.9,11.842,-.05],face:'top',name:'C124 supplied original 402x146 conformity ink',artworkKind:'official-raster'});
 host.atomS3LiteAssembly.labelCarriers=[carrier,side];host.atomS3LiteAssembly.artworkPanels=[back,certification].filter(Boolean);
}
