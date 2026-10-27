import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh,slab,FACE} from '../../modeling/parts.js';
import {printedArtwork} from '../../modeling/artwork.js';
const portA=new URL('./reference-redraw-port-a.png',import.meta.url).href,pwr485=new URL('./reference-redraw-pwr485.png',import.meta.url).href,debug=new URL('./reference-redraw-debug.png',import.meta.url).href;
/** Actual adhesive carriers exist independently of the optional PNG ink layers. */
export function addStickers(host){
 const material=materials.plastic(0xd1d2cb,{roughness:.86}),panels=[],carriers=[];
 const add=(id,url,size,position,face,rotation=0)=>{
  const carrier=slab(host.body,size[0],size[1],.04,.08,position,material,[],0);carrier.quaternion.copy(FACE[face]).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),rotation));carrier.name=`Roller485-Lite physical ${id} adhesive substrate`;carrier.userData.role='physical-adhesive-substrate';carriers.push(carrier);
  panels.push(...(printedArtwork(host,{target:carrier,url,size,position,face,rotation,depth:.14,artworkKind:'reference-redraw',name:`Roller485-Lite fixed ${id} print (own U182-Lite photograph redraw)`})??[]));return carrier;
 };
 add('PORT.A',portA,[7.2,9.2],[0,-19.8,15.9],'bottom',Math.PI/2);
 add('PWR485',pwr485,[16,9.2],[14.85,-19.8,0],'bottom',Math.PI/2);
 // The real ISP label is an open U around the debug mouth. This is an open
 // outline notch, so neither substrate nor PNG spans a connector opening.
 const s=new THREE.Shape();s.moveTo(-8,2.9);s.lineTo(-8,-2.9);s.lineTo(-4.5,-2.9);s.lineTo(-4.5,.8);s.lineTo(4.5,.8);s.lineTo(4.5,-2.9);s.lineTo(8,-2.9);s.lineTo(8,2.9);s.closePath();
 const carrier=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.04,bevelEnabled:false}),material,[0,-13.35,-19.805],'Roller485-Lite physical ISP adhesive substrate with open mouth');carrier.quaternion.copy(FACE.back);carrier.userData.role='physical-adhesive-substrate';carriers.push(carrier);
 panels.push(...(printedArtwork(host,{target:carrier,url:debug,size:[16,5.8],position:[0,-13.35,-19.825],face:'back',depth:.14,artworkKind:'reference-redraw',name:'Roller485-Lite fixed ISP print (own U182-Lite 12.webp redraw)'})??[]));host.stickerCarriers=carriers;return panels;
}
