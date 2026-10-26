import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {slab,mesh,disc,FACE} from '../../modeling/parts.js';
import {usbC,microSD,audioJack} from '../../modeling/connectors.js';
import {physicalButton} from '../../modeling/actuators.js';

// Product-specific assembly inserts. Apertures come from the selected official
// K132-Adv enclosure; concealed depths are appearance estimates, not fit data.
function ring(parent,{x,y,z,outer,inner,depth,material,name,face='front',hex=false}){
 const group=new THREE.Group();group.position.set(x,y,z);group.quaternion.copy(FACE[face]);group.name=name;parent.add(group);
 const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);const hole=new THREE.Path();
 if(hex){for(let i=0;i<6;i++){const a=-i*Math.PI/3;const p=[inner*Math.cos(a),inner*Math.sin(a)];i?hole.lineTo(...p):hole.moveTo(...p);}hole.closePath();}else hole.absarc(0,0,inner,0,Math.PI*2,true);
 shape.holes.push(hole);mesh(group,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,[0,0,-depth],`${name} bored body`);
 mesh(group,new THREE.CircleGeometry(inner,32),materials.plastic(0x0e1311,{roughness:.95}),[0,0,-depth-.03],`${name} recessed floor`);
 return group;
}

export function addStampAssembly(host){
 const black=materials.plastic(0x1d2420,{roughness:.9}),silver=materials.metal(0xb5bcba,{roughness:.48});
 const group=new THREE.Group();host.body.add(group);group.name='StampS3A assembled board and antenna';
 slab(group,23.2,17.2,.8,.3,[27.8,16.47,5.18],black,[],.04).name='StampS3A black PCB';
 // The CAD already contains the actual molded cover and central button. Its
 // long, empty antenna pocket faces away from USB; it is not a generic shield.
 slab(group,6.1,14.6,3.1,.12,[19.75,16.8,5.98],black,[],.025).name='StampS3A antenna carrier';
 const antenna=new THREE.Shape();antenna.moveTo(-2.85,-7.05);antenna.lineTo(2.85,-7.05);antenna.lineTo(2.85,-.65);antenna.lineTo(1.35,-.65);antenna.lineTo(1.35,.65);antenna.lineTo(2.85,.65);antenna.lineTo(2.85,7.05);antenna.lineTo(-2.85,7.05);antenna.closePath();
 mesh(group,new THREE.ExtrudeGeometry(antenna,{depth:.5,bevelEnabled:true,bevelThickness:.025,bevelSize:.025,bevelSegments:1}),silver,[19.75,16.8,9.1],'StampS3A U-notched 3D antenna');
 ring(group,{x:31.3,y:20.97,z:9.4,outer:1.53,inner:.64,depth:.55,material:silver,name:'StampS3A retaining hex screw',hex:true});
 const gold=materials.metal(0xa99153,{roughness:.46});
 for(const y of [8.47,24.47])for(let i=0;i<9;i++){
  const shape=new THREE.Shape();shape.absarc(0,0,.58,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.28,0,Math.PI*2,true);shape.holes.push(bore);
  mesh(group,new THREE.ExtrudeGeometry(shape,{depth:.07,bevelEnabled:false,curveSegments:16}),gold,[27.8+(i-4)*2.54,y,5.99],'StampS3A plated edge contact');
 }
 slab(group,1.5,1.5,.55,.18,[35.25,10.45,7.8],materials.glossy(0xd4d7c8,{roughness:.35}),[],.03).name='StampS3A RGB package';
 // y 12.0…20.9, z 6.1…9.6 is the true +X USB aperture. The previous
 // shallow insert at z 4.2 landed on an uninterrupted part of the white shell.
 return usbC(host,{id:'usb',position:[42.02,16.47,7.85],face:'right',w:8.65,h:3.05,depth:6.5});
}

export function addInternalAssembly(host){
 const dark=materials.plastic(0x111a16,{roughness:.95});
 // The official printable shell leaves its assembling seam open between the
 // snap features. A recessed structural lap joins those walls in the finished
 // product. Keep the real audio opening and EXT mouth clear of the lap.
 const lap=materials.plastic(0x25292a,{roughness:.82});
 const seam=(size,position,label)=>{const o=mesh(host.body,new THREE.BoxGeometry(...size),lap,position,`Inner enclosure seam lap ${label}`);o.userData.role='assembly-seam-lap';return o;};
 seam([.9,51.6,1.1],[-40.8,0,-1.3],'left');
 seam([.9,39.4,1.1],[40.8,-6.1,-1.3],'right lower');
 seam([.9,6.2,1.1],[40.8,22.7,-1.3],'right upper');
 seam([.9,6,.45],[40.8,16.6,-.975],'above audio');
 seam([81.6,.9,1.1],[0,-25.6,-1.3],'bottom');
 for(const sign of [-1,1])seam([31.3,.9,1.1],[sign*25.15,25.6,-1.3],`top ${sign<0?'left':'right'}`);
 // This bridge sits behind the shallow EXT housing and above its upper bores,
 // closing the small clearance above the socket without covering any lead-in.
 seam([19.2,.65,1.1],[0,24.35,-1.3],'behind EXT roof');
 for(const sign of [-1,1])seam([.7,1.9,1.1],[sign*9.65,25,-1.3],`beside EXT ${sign<0?'left':'right'}`);
 const board=new THREE.Shape();for(const [i,p]of [[-40.1,-25.1],[40.1,-25.1],[40.1,12],[36.4,12],[36.4,21.4],[40.1,21.4],[40.1,25.1],[-40.1,25.1],[-40.1,24.6],[-35.5,24.6],[-35.5,13.4],[-40.1,13.4]].entries())i?board.lineTo(...p):board.moveTo(...p);board.closePath();
 mesh(host.body,new THREE.ExtrudeGeometry(board,{depth:1,bevelEnabled:false}),materials.plastic(0x2c4a3b,{roughness:.9}),[0,0,1],'Main PCB with Grove and speaker clearance');
 // One 1500 mAh battery in the ADV. This conservative internal envelope keeps
 // clear of the audio receptacle and upper mounting features.
 slab(host.body,66,28,6,2.5,[-2,-8,-7.5],materials.plastic(0x7f8784,{roughness:.83}),[],.3).name='1500 mAh battery visual envelope';
 const speaker=slab(host.body,8.6,5.4,1.35,1.4,[38.9,16.5,2.7],dark,[],.08);speaker.quaternion.copy(FACE.right);speaker.name='Speaker acoustic enclosure';
 // Every one of the thirteen source-CAD holes retains ~1.7 mm of depth in
 // front of the assembled dark speaker body rather than exposing a green PCB.
 // The neighboring narrow left-side aperture is the schematic SW2 Grove
 // +5VIN/+5VOUT selector. Its cap travels along the long axis of the CAD slot.
 const selector=new THREE.Group();selector.position.set(-41.9,8,0);selector.quaternion.copy(FACE.left);host.body.add(selector);selector.name='Grove SW2 slide-switch carrier';
 slab(selector,4,1.55,1.7,.12,[0,0,-1.7],dark,[{w:3.45,h:1.08,r:.1}],.015).name='SW2 slotted switch body';
 mesh(selector,new THREE.BoxGeometry(3.45,1.08,.2),dark,[0,0,-1.8],'SW2 deep slot floor');
 const cap=slab(host.body,1.15,.9,1,.1,[-41,7.3,0],materials.plastic(0xbec5bd,{roughness:.68}),[],.03);cap.quaternion.copy(FACE.left);cap.name='Grove SW2 selector cap';
 physicalButton(host,{id:'grove-power',label:'Grove +5V direction selector · visual detents only',mesh:cap,axis:[0,1,0],travel:1.4,latching:true,meta:{surfaceCenter:[-42,7.3,0],surfaceFace:'left',mechanism:'slide',schematicRef:'SW2',detents:['+5VOUT','+5VIN'],electricalBehavior:false}});
 microSD(host,{id:'micro-sd',position:[-12.8,26.85,0],face:'top',w:12.6,h:1.4,depth:7.2});
 audioJack(host,{id:'headset',position:[42.03,16.6,-4],face:'right',diameter:5.35,bore:3.5,depth:8.5});
 const ir=new THREE.Group();ir.position.set(-32.4,26.1,.45);host.body.add(ir);ir.name='Infrared emitter assembly';
 mesh(ir,new THREE.CylinderGeometry(.83,.83,1.2,32),materials.plastic(0x252e27,{roughness:.5}),[0,-.6,0],'IR emitter cylindrical package');
 mesh(ir,new THREE.SphereGeometry(.81,32,20,0,Math.PI*2,0,Math.PI/2),materials.glossy(0x7b8a7d,{roughness:.16}),[0,0,0],'IR emitter domed lens');
 // Four actual rear mounting bores stay open at the mouth and gain recessed
 // dark floors. The separate, smaller U-shaped recesses carry brass inserts.
 for(const x of [-36,-20,20,36]){
  const o=disc(host.body,2.7,[x,23,-4.6],dark);o.quaternion.copy(FACE.back);o.name='Rear mounting blind-hole floor';
 }
 for(const x of [-28,28])ring(host.body,{x,y:23,z:-6.05,outer:1.18,inner:.72,depth:3.1,material:materials.metal(0xab9349,{roughness:.43}),name:'Rear brass threaded mounting insert',face:'back'});
 for(const x of [-29,12.4])ring(host.body,{x,y:9.4,z:-7.86,outer:1.46,inner:.59,depth:.45,material:materials.metal(0xa5adab,{roughness:.4}),name:'Rear enclosure hex screw',face:'back',hex:true});
}
