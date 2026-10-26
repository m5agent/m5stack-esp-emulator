import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedSlab} from '../../core/geometry.js';
import {FACE,mesh,slab} from '../../modeling/parts.js';

// Concealed thicknesses are visual, photo-derived assembly estimates. They are
// not PCB layouts or fabrication dimensions; real case and port openings remain.
export function addAssembly(host,d){
 slab(host.body,d.w+.65,d.h+.65,.88,.3,[d.cx,d.cy,3.03],materials.plastic(0x555e5a,{roughness:.9}),[],.035).name='EPD module body';
 const outline=new THREE.Shape();outline.moveTo(-26.4,-46.3);outline.lineTo(-24.6,-46.3);outline.lineTo(-24.6,-44.8);outline.lineTo(-13.8,-44.8);outline.lineTo(-13.8,-46.3);outline.lineTo(27.4,-46.3);outline.lineTo(27.4,46.3);outline.lineTo(-26.4,46.3);outline.lineTo(-26.4,-26.3);outline.lineTo(-22.6,-26.3);outline.lineTo(-22.6,-39.7);outline.lineTo(-26.4,-39.7);outline.closePath();
 mesh(host.body,new THREE.ExtrudeGeometry(outline,{depth:.6,bevelEnabled:false}),materials.plastic(0x1c443d,{roughness:.9}),[0,0,-1.3],'Visual main PCB with connector clearances');
 slab(host.body,55.4,35.8,.5,1.5,[.5,-29.4,-3.34],materials.plastic(0x3f4237,{roughness:.95}),[],.03).name='NFC carrier board';

 // A recessed tube and package retain the microphone's genuine acoustic bore.
 const mic=new THREE.Group();mic.name='MIC acoustic package';mic.position.set(-29.45,18,0);mic.quaternion.copy(FACE.left);host.body.add(mic);
 const ring=new THREE.Shape();ring.absarc(0,0,.49,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.3,0,Math.PI*2,true);ring.holes.push(bore);
 mesh(mic,new THREE.ExtrudeGeometry(ring,{depth:1.15,bevelEnabled:false,curveSegments:32}),materials.plastic(0x151c1a,{roughness:.95}),[0,0,-1.15],'MIC acoustic tube');
 mesh(mic,new THREE.CylinderGeometry(.34,.34,.18,32).rotateX(Math.PI/2),materials.plastic(0x090e0b,{roughness:1}),[0,0,-1.24],'MIC recessed diaphragm');
 slab(mic,2.2,1.8,.5,.2,[0,0,-1.82],materials.metal(0x858c85,{roughness:.75}),[],.025).name='MEMS microphone body';
}

export function rgbGuide(){
 const lens=new THREE.Mesh(roundedSlab({w:8.15,h:2.15,depth:.9,radius:1.05,holes:[],bevel:.03}).translate(0,0,-.9),materials.plastic(0xb4bdb4,{roughness:.62,clearcoat:.18,transmission:.14,thickness:.9}));
 lens.name='RGB long light guide';return lens;
}
