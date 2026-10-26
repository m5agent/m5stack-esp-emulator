import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {FACE,mesh,slab} from '../../modeling/parts.js';

// Partial boards and concealed packages close observed apertures without
// claiming a complete internal layout. Their local depths are photo-derived.
export function addAssembly(host,d){
 slab(host.body,d.w+.65,d.h+.65,.9,.3,[d.cx,d.cy,3.28],materials.plastic(0x56635b,{roughness:.92}),[],.035).name='EPD module body';
 slab(host.body,63,19.5,.6,1.4,[.4165,37,-1.65],materials.plastic(0x21473d,{roughness:.92}),[],.03).name='Upper visual PCB';
 const lower=new THREE.Shape();lower.moveTo(-31,-47);lower.lineTo(17.9,-47);lower.lineTo(17.9,-44.3);lower.lineTo(31.5,-44.3);lower.lineTo(31.5,-23);lower.lineTo(-31,-23);lower.closePath();
 mesh(host.body,new THREE.ExtrudeGeometry(lower,{depth:.6,bevelEnabled:false}),materials.plastic(0x21473d,{roughness:.92}),[0,0,-2.1],'Lower visual PCB with Grove clearance');

 // The top band of the bottom badge recess is genuinely open in the STL.
 // Give it a solid recessed insert; artwork is deferred until originals arrive.
 const insert=slab(host.body,31.6,1.95,1.2,.18,[.4165,-51.64,1.75],materials.plastic(0xd4d8ce,{roughness:.8}),[],.03);insert.quaternion.copy(FACE.bottom);insert.geometry.translate(0,0,-1.2);insert.name='Bottom aperture molded insert';
 const surround=new THREE.Group();surround.position.set(24.7665,-51.951,-.75);surround.quaternion.copy(FACE.bottom);surround.name='Grove metal package';host.body.add(surround);
 slab(surround,12.6,6.3,2.4,.3,[0,0,-2.35],materials.metal(0x939d98,{roughness:.54}),[{w:10.18,h:5.22,r:.08,cx:0,cy:0}],.035).name='Grove retaining surround';

 const speaker=new THREE.Group();speaker.name='Speaker acoustic enclosure';speaker.position.set(34.15,-16.25,.1);speaker.quaternion.copy(FACE.right);host.body.add(speaker);
 slab(speaker,11.6,4.5,1.4,.6,[0,0,-1.4],materials.plastic(0x1a211d,{roughness:.95}),[{w:9.8,h:2.9,r:.3,cx:0,cy:0}],.04).name='Speaker acoustic frame';
 slab(speaker,10.2,3.2,.3,.3,[0,0,-.9],materials.plastic(0x111914,{roughness:1}),[],.025).name='Speaker recessed diaphragm';
 slab(speaker,11.2,4.1,.25,.4,[0,0,-1.65],materials.plastic(0x262d25,{roughness:.94}),[],.025).name='Speaker enclosure rear';

 const sensor=new THREE.Group();sensor.name='SHT40 vent assembly';sensor.position.set(21.4,49.85,-.05);sensor.quaternion.copy(FACE.top);host.body.add(sensor);
 slab(sensor,8.1,3.2,.35,.25,[0,0,-1.8],materials.plastic(0x1c433a,{roughness:.9}),[],.02).name='SHT40 local carrier';
 slab(sensor,7.6,2.8,.25,.2,[0,0,-.25],materials.metal(0x6b766e,{roughness:.82}),[-1.9,0,1.9].map(cx=>({w:.7,h:1.5,r:.2,cx,cy:0})),.02).name='SHT40 perforated inlet guard';
 slab(sensor,3,2.7,.5,.2,[0,0,-1.1],materials.plastic(0x242b23,{roughness:.96}),[],.02).name='SHT40 sensor package';

 const mic=new THREE.Group();mic.name='MIC acoustic package';mic.position.set(-19.6,50.3,.25);mic.quaternion.copy(FACE.top);host.body.add(mic);
 const ring=new THREE.Shape();ring.absarc(0,0,.56,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.33,0,Math.PI*2,true);ring.holes.push(bore);
 mesh(mic,new THREE.ExtrudeGeometry(ring,{depth:1.15,bevelEnabled:false,curveSegments:32}),materials.plastic(0x131b15,{roughness:.96}),[0,0,-1.15],'MIC acoustic tube');
 mesh(mic,new THREE.CylinderGeometry(.35,.35,.18,32).rotateX(Math.PI/2),materials.plastic(0x0b100c,{roughness:1}),[0,0,-1.24],'MIC recessed diaphragm');
 slab(mic,2.3,2,.45,.2,[0,0,-1.75],materials.metal(0x7c877c,{roughness:.75}),[],.02).name='MEMS microphone body';
 for(const x of [-31.4,32.25])slab(host.body,1.6,1.6,.65,.2,[x,48,-.3],materials.plastic(0xe0e5cc,{roughness:.6}),[],.03).name='RGB emitter package';
}
