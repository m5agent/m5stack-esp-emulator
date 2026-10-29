// MIT code; ordinary own-photo reference-redraw PNG. Graphic/trademark rights retained.
import {printedFilm} from '../../modeling/artwork.js';
import {materials,FACE,plate,cylinder} from './geometry.js';
export function addStickers(host){
 const a=host.atomS3RExtAssembly,carriers=[];
 const p=[0,3,-5.815],rear=plate(host.body,12,15,.025,p,materials.plastic(0xd8dad5,{roughness:.83}),'C126-Ext real rear adhesive substrate with M2 diecut',{radius:.03,holes:[{radius:1.13,x:0,y:-3}]});rear.quaternion.copy(FACE.back);carriers.push(rear);
 const cp=[1,11.815,-.3],side=plate(host.body,13.4,6.4,.025,cp,materials.plastic(0xd8dad5,{roughness:.83}),'C126-Ext real conformity adhesive substrate',{radius:.025});side.quaternion.copy(FACE.top);carriers.push(side);
 for(const c of carriers)c.userData.visualFamily='label-substrate';
 a.labelCarriers=carriers;a.artworkPanels=[
 printedFilm(host,{url:new URL('./artwork/rear.png',import.meta.url).href,size:[12,15],position:[0,3,-5.85],face:'back',holes:[{w:2.26,h:2.26,r:1.13,cx:0,cy:-3}],name:'C126-Ext rear own-photo reference redraw',artworkKind:'reference-redraw'}),
 printedFilm(host,{url:new URL('./artwork/compliance.png',import.meta.url).href,size:[13.4,6.4],position:[1,11.85,-.3],face:'top',name:'C126-Ext conformity own-photo reference redraw',artworkKind:'reference-redraw'}),
 printedFilm(host,{url:new URL('./artwork/prototype.png',import.meta.url).href,size:[21,21],position:[0,0,5.80],holes:a.protoHoles.map(h=>({w:.92,h:.92,r:.46,cx:h.x,cy:h.y})),name:'C126-Ext prototype own-photo silkscreen redraw',artworkKind:'reference-redraw'})].filter(Boolean);
}
