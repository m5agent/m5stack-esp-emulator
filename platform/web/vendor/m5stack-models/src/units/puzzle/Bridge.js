import * as THREE from 'three';
import {Device,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {slab,mesh} from '../../modeling/parts.js';
import {printedArtwork} from '../../modeling/artwork.js';
import data from './bridge-geometry-data.js';
const label=new URL('./reference-redraw-bridge.png',import.meta.url).href;
/** One supplied rigid joining accessory. Standalone appearance;no invented fit Port. */
export class Bridge extends Device{
 static meta={id:'m5stack.unit.puzzle.bridge',name:'Unit Puzzle supplied rigid joining accessory',sku:'U193 accessory',vendor:'M5Stack',size:[10.000008,14.000037,7.500001],keymap:{},scope:'standalone-physical-appearance'};
 build(){
  const parts=addCadParts(this,data,{carrier:materials.plastic(0xe9ebe4,{roughness:.74}),cover:materials.plastic(0xe7e9e2,{roughness:.76})}),boardShape=roundedRect(9.3,13.3,.2),hole=new THREE.Path();hole.absarc(0,0,1.15,0,Math.PI*2,false);boardShape.holes.push(hole);
  const pcb=mesh(this.body,new THREE.ExtrudeGeometry(boardShape,{depth:.65,bevelEnabled:false,curveSegments:32}),materials.plastic(0x252923,{roughness:.9}),[0,0,-1.25],'Puzzle Bridge actual joining PCB with central drilling'),headers=[],contacts=[];
  for(const y of[-4.8,4.8]){
   const holes=[-3,-1,1,3].map(x=>({cx:x,cy:0,w:.88,h:.88,r:.04})),housing=slab(this.body,8.6,2.3,2.15,.1,[0,y,1.45],materials.plastic(0x161b18,{roughness:.8}),holes,.02);housing.name=`Puzzle Bridge actual four-chamber female contact strip ${y<0?'A':'B'}`;headers.push(housing);
   for(const x of[-3,-1,1,3]){for(const sign of[-1,1])contacts.push(mesh(this.body,new THREE.BoxGeometry(.08,.58,1.45),materials.metal(0xb8ad85,{roughness:.46}),[x+sign*.29,y,2.22],'Puzzle Bridge recessed female spring contact'));mesh(this.body,new THREE.BoxGeometry(.6,.6,.08),materials.plastic(0x20251e),[x,y,1.5],'Puzzle Bridge recessed contact chamber floor');}
  }
  this.bridgeAssembly={parts,pcb,headers,contacts};this.unitStickers=printedArtwork(this,{target:parts['Puzzle Bridge complete native rear retaining cap'],url:label,size:[8.7,12.7],position:[0,0,-3.75],face:'back',depth:.25,name:'Puzzle Bridge rear maker and pin marks reference redraw',artworkKind:'reference-redraw'})??[];
 }
}
export default Bridge;
