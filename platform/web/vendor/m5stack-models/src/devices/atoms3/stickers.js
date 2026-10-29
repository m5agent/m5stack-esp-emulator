// MIT code. Flattened ordinary PNG only; M5Stack graphic and trademark rights remain theirs.
// C123 own-current-photo redraw and converter glyph repair. No vector/table/name/URL mapping ships.
import {printedFilm} from '../../modeling/artwork.js';
import {materials,FACE,plate} from './geometry.js';
import {DIM} from './dimensions.js';
export function addStickers(host){
 const a=host.atomS3Assembly,size=[12,15],p=DIM.rearLabel,hole={radius:1.13,x:0,y:-3};
 const carrier=plate(host.body,...size,.025,p,materials.plastic(0xd8dad5,{roughness:.83}),'C123 real rear adhesive substrate with true M2 bore',{radius:.03,holes:[hole]});carrier.quaternion.copy(FACE.back);carrier.userData.visualFamily='label-substrate';
 const rear=printedFilm(host,{url:new URL('./artwork/rear.png',import.meta.url).href,size,position:[0,3,p[2]-.031],face:'back',holes:[{w:2.26,h:2.26,r:1.13,cx:0,cy:-3}],name:'C123 rear ink current-photo GC9107 reference redraw',artworkKind:'reference-redraw'});
 const cs=[14.1,9.2],cp=DIM.compliance,side=plate(host.body,...cs,.025,cp,materials.plastic(0xd8dad5,{roughness:.84}),'C123 real conformity adhesive substrate',{radius:.025});side.quaternion.copy(FACE.top);side.userData.visualFamily='label-substrate';
 const compliance=printedFilm(host,{url:new URL('./artwork/compliance.png',import.meta.url).href,size:cs,position:[cp[0],cp[1]+.031,cp[2]],face:'top',name:'C123 conformity ink glyph-repaired flat reference',artworkKind:'reference-redraw'});
 const flex=printedFilm(host,{url:new URL('./artwork/lcd-flex.png',import.meta.url).href,size:[17.5,1.1],position:[0,-11.927,4.4],parent:a.button.cap.children.find(o=>o.name==='C123 complete pressable LCD stack'),face:'bottom',name:'C123 folded LCD flex stripe reference redraw',artworkKind:'reference-redraw'});
 a.labelCarriers=[carrier,side,a.lcdFlex];a.artworkPanels=[rear,compliance,flex].filter(Boolean);
}
