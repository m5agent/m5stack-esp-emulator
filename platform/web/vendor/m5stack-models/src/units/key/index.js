import * as THREE from 'three';
import {Device,Module,Component,Button,Led,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,mesh,slab,screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {roundedRect} from '../../core/geometry.js';
import {keycapGeometry,switchWallGeometry} from './key-geometry.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

function board(host){
 const shape=new THREE.Shape(),w=9.9,h=18.2,r=2.6,n=5.3,bore=4.1,edgeOffset=w-8,dy=Math.sqrt(bore*bore-edgeOffset*edgeOffset),theta=Math.acos(edgeOffset/bore);
 shape.moveTo(-w+r,-h);shape.lineTo(-n,-h);shape.lineTo(-n,-13.3);shape.lineTo(n,-13.3);shape.lineTo(n,-h);shape.lineTo(w-r,-h);
 // Clear the native bosses' outside diameter as well as their through-bores.
 // These circles cross the narrow PCB edge and must be open outline notches.
 shape.absarc(w-r,-h+r,r,-Math.PI/2,0);shape.lineTo(w,-8-dy);shape.absarc(8,-8,bore,-theta,theta-Math.PI*2,true);shape.lineTo(w,h-r);shape.absarc(w-r,h-r,r,0,Math.PI/2);shape.lineTo(-w+r,h);shape.absarc(-w+r,h-r,r,Math.PI/2,Math.PI);shape.lineTo(-w,-8+dy);shape.absarc(-8,-8,bore,Math.PI-theta,-Math.PI+theta,true);shape.lineTo(-w,-h+r);shape.absarc(-w+r,-h+r,r,Math.PI,Math.PI*1.5);
 for(const [x,y,radius]of [[0,-8,3.1],[0,8,1.9],[-4,10.5,.8],[2.9,13,.8]]){const hole=new THREE.Path();hole.absarc(x,y,radius,0,Math.PI*2,true);shape.holes.push(hole);}
 // The native front's four locating bosses reach down to Z=-1 mm. Keep the
 // board top at -1.1 mm, while clearing the rear floor at Z=-2.8 mm.
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x275142,{roughness:.9}),[0,0,-1.9],'Key circuit board with Grove clearance and physical bores');host.parts.pcb=pcb;
 const metal=materials.metal(0xbab8a5,{roughness:.5});
 for(const [x,y]of [[-4,10.5],[2.9,13]]){const post=new THREE.CylinderGeometry(.56,.56,4.7,20).rotateX(Math.PI/2);mesh(host.body,post,metal,[x,y,-1.45],'Key fixed switch solder tail through native rear aperture');}
 mesh(host.body,new THREE.CylinderGeometry(1.6,1.6,5.4,32).rotateX(Math.PI/2),materials.plastic(0xd5dad1),[0,8,-1.1],'Key fixed switch center locating post');
}

function switchAndCap(host){
 const clear=materials.plastic(0xe4eee7,{roughness:.19,clearcoat:.5,transparent:true,opacity:.42,depthWrite:false}),dark=materials.plastic(0x323b38,{roughness:.72});
 const foot=slab(host.body,16.1,16.1,.45,1.6,[0,8,4.0],materials.plastic(0xe7eae1),[{w:13.1,h:13.1,r:.5}],.035);foot.name='Key fixed switch mounting flange';host.parts.switchFoot=foot;
 const lower=slab(host.body,14.1,14.1,3.2,.65,[0,8,1.15],dark,[{w:12.0,h:12.0,r:.35}],.045);lower.name='Key fixed lower switch package with clear center';
 const walls=mesh(host.body,switchWallGeometry(),clear,[0,8,0],'Key clear switch enclosure with 0.8 mm walls');host.parts.switchHousing=walls;
 const roof=slab(host.body,12.6,12.6,.4,.8,[0,8,9.25],clear,[{w:5.3,h:5.3,r:.22}],.025);roof.name='Key fixed clear guide roof with real stem opening';
 for(const x of [-7.15,7.15])slab(host.body,.65,3.4,1.65,.15,[x,8,5.1],clear,[],.025).name='Key fixed clear switch side latch';
 for(const y of [1.0,15.0])mesh(host.body,new THREE.BoxGeometry(4.3,.45,.8),clear,[0,y,4.8],'Key fixed clear lower latch');
 // Contacts remain recessed in the fixed package. The central moving stem
 // has an actual clear chamber, rather than penetrating a solid hidden box.
 for(const x of [-4.6,4.6])mesh(host.body,new THREE.BoxGeometry(.35,5.2,2.0),materials.metal(0xa5a28e,{roughness:.47}),[x,8,2.2],'Key fixed recessed switch contact');
 const cap=new THREE.Group();cap.name='Key moving red keycap and blue stem';
 const red=materials.plastic(0xa6292c,{roughness:.65,clearcoat:.12}),blue=materials.plastic(0x008bc2,{roughness:.55});
 mesh(cap,keycapGeometry(),red,[0,0,0],'Key red sculpted cap with concave top and open underside');
 // The red stem receiver is joined to the cap's inner ceiling, and its real
 // cross-shaped bore receives the blue moving stem from below.
 const receiver=roundedRect(5.8,5.8,.2),cross=new THREE.Path();
 cross.moveTo(-.65,-2.3);cross.lineTo(-.65,-.65);cross.lineTo(-2.3,-.65);cross.lineTo(-2.3,.65);cross.lineTo(-.65,.65);cross.lineTo(-.65,2.3);cross.lineTo(.65,2.3);cross.lineTo(.65,.65);cross.lineTo(2.3,.65);cross.lineTo(2.3,-.65);cross.lineTo(.65,-.65);cross.lineTo(.65,-2.3);cross.closePath();receiver.holes.push(cross);
 mesh(cap,new THREE.ExtrudeGeometry(receiver,{depth:3.1,bevelEnabled:false}),red,[0,0,4.0],'Key red hollow cross stem receiver');
 slab(cap,4.5,4.5,3.1,.25,[0,0,-2.7],blue,[],.035).name='Key moving blue switch slider';
 for(const [w,h]of [[4.35,1.18],[1.18,4.35]])mesh(cap,new THREE.BoxGeometry(w,h,6.8),blue,[0,0,3.5],'Key moving blue cross stem');
 const button=host.add(new Button({id:'press',label:'Mechanical key',mesh:cap,position:spec.keyPosition,travel:spec.travelMm,meta:{role:'visual-control',actuation:'momentary',surfaceCenter:[0,8,20.1],surfaceFace:'front',travelSource:'1.6 mm appearance-only estimate; official blue-switch part/travel not supplied',geometrySource:'U144 official mechanical drawing and cap-on/cap-off photographs; no keycap CAD'}}));
 host.keyMechanism={button,clearWalls:walls,roof,lower};
 const ledPackage=slab(host.body,3.5,3.5,.8,.2,[0,3.5,4.4],materials.plastic(0xdde2ce),[],.035);ledPackage.name='Key fixed SK6812 package under clear switch';
 const lens=new THREE.Mesh(new THREE.BoxGeometry(2.4,2.4,.18),materials.plastic(0xcdd6b4,{roughness:.36}));lens.name='Key fixed RGB lens';
 host.add(new Led({id:'rgb',label:'Key RGB',mesh:lens,position:spec.rgb,glowSize:5,meta:{role:'externally-driven-visual',source:'Official key_01 points to RGB beneath the clear front of the switch',positionEvidence:'Photo-derived local position; no press-to-light behavior'}}));
}

function build(host){
 addCadParts(host,data,{shell:materials.plastic(0xe3e7df,{roughness:.79})});board(host);switchAndCap(host);
 const socket=grove(host,{...spec.grove,color:0x202724});socket.name='Key native bottom Grove assembly';
 // This connector has the photographed open upper face. Its rear wall and
 // four metal pins remain real; only the shared helper's full roof is omitted.
 const cover=socket.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);if(!cover)throw new Error('Key Grove roof was not found');const plastic=cover.material;cover.removeFromParent();cover.geometry.dispose();
 for(const x of [-3.85,3.85])mesh(socket,new THREE.BoxGeometry(.9,.8,5.8),plastic,[x,2.1,-2.9],'Key Grove open upper side rail');
 mesh(socket,new THREE.BoxGeometry(3.4,.65,1.05),plastic,[0,1.1,-3.5],'Key Grove short latch bridge');
 for(const x of [-3,-1,1,3])mesh(host.body,new THREE.BoxGeometry(.42,1.2,1.3),materials.metal(0xb0b5a3,{roughness:.5}),[x,-13.6,-1.4],'Key fixed Grove PCB tail');
 screw(host.body,[0,-8,-4.015],'back',1.25);
 host.add(new Component({id:'sensor',label:'Unit Key visual anchor',meta:{role:'visual-anchor',scope:'no-keyboard-firmware-or-electrical-behavior'}}));
 addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.key',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:spec.keymap};
 build(){build(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.key.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:spec.keymap};
 build(options={}){buildGroveModuleAssembly(this,build,options);}
}
export {spec};
export default Model;
