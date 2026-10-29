// MIT code. Approved flattened ordinary PNG only;private table/vector/original mappings excluded.
import {printedFilm} from '../../modeling/artwork.js';
import {materials,FACE,plate} from './geometry.js';
export function addStickers(host){const a=host.atomS3UAssembly,p=[0,6.3,-4.965],size=[15.3,35],carrier=plate(host.body,...size,.025,p,materials.plastic(0xe1e4dc,{roughness:.85}),'K125 actual rear adhesive physical carrier',{radius:.6});carrier.quaternion.copy(FACE.back);carrier.userData.visualFamily='label-substrate';a.labelCarriers=[carrier];a.artworkPanels=[printedFilm(host,{url:new URL('./artwork/rear.png',import.meta.url).href,size,position:[0,6.3,-5.0],face:'back',name:'K125 approved ordinary rear graphic raster',artworkKind:'approved-ordinary-raster'})].filter(Boolean);}
