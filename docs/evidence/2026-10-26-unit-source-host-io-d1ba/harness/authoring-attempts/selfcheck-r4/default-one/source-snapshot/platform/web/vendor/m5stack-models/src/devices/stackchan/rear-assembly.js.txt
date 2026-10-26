import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {slab,mesh,FACE,screw} from '../../modeling/parts.js';

// Connector placement is photo-derived. These are visual bodies only.
function connector(parent,{name,position,pins,pitch,width,height,color,face='back'}){
 const group=new THREE.Group();group.name=name;group.position.fromArray(position);group.quaternion.copy(FACE[face]);parent.add(group);
 const plastic=materials.plastic(color,{roughness:.8});
 slab(group,width,height,.25,.25,[0,0,0],plastic,[],.04).name=`${name} backstop`;
 slab(group,width,height,.95,.25,[0,0,.25],plastic,[{w:width-1.2,h:height-1.3,r:.15}],.06).name=`${name} shroud`;
 const metal=materials.metal(0x9d9a7c,{roughness:.46});group.contacts=[];
 for(let i=0;i<pins;i++)group.contacts.push(mesh(group,new THREE.BoxGeometry(.42,.38,.7),metal,[(i-(pins-1)/2)*pitch,-.15,.67],`${name} contact ${i+1}`));
 slab(group,width*.48,.48,.5,.12,[0,height/2-.18,.62],plastic,[],.04).name=`${name} latch`;
 group.userData={role:'visual-cable-connector',contactCount:pins,pitchMm:pitch,placementSource:'official A180 rear/front photos; concealed dimensions inferred'};return group;
}

export function addRearAssembly(host){
 const rear=new THREE.Group();rear.name='Rear body electronics';host.body.add(rear);
 // A180 photos 05/08/09 locate this board on the Core attachment plane. It
 // must not be pasted over the genuinely open rear at Z -29.3. The selected
 // head shell seats at Z15.95; the PCB sits immediately in front of that
 // flange, not embedded in its 0.8 mm rear lip. Core headers mate above it.
 const shape=new THREE.Shape(),r=2.2;shape.moveTo(-22.3,-16.25);shape.lineTo(22.3,-16.25);shape.absarc(22.3,-14.05,r,-Math.PI/2,0);shape.lineTo(24.5,30.55);shape.absarc(22.3,30.55,r,0,Math.PI/2);
 // Open edge notches clear the whole Grove housing, including its rear wall;
 // contacts bend below the notch before landing on the PCB. Concealed outline
 // is inferred, and never changes the original shell aperture or Grove frame.
 for(const [x,y]of [[16.2,32.75],[16.2,29],[5.8,29],[5.8,32.75],[-5.8,32.75],[-5.8,29],[-16.2,29],[-16.2,32.75],[-22.3,32.75]])shape.lineTo(x,y);
 shape.absarc(-22.3,30.55,r,Math.PI/2,Math.PI);shape.lineTo(-24.5,-14.05);shape.absarc(-22.3,-14.05,r,Math.PI,Math.PI*1.5);shape.closePath();
 for(const x of [-21,21])for(const y of [-12.75,29.25]){const hole=new THREE.Path();hole.absarc(x,y,1.5,0,Math.PI*2,true);shape.holes.push(hole);}
 shape.holes.push(roundedRect(9,14,.6,{cx:0,cy:-2.5,path:new THREE.Path(),clockwise:true}));
 mesh(rear,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x253d30,{roughness:.91}),[0,0,16.0],'Rear power PCB');
 for(const x of [-21,21])for(let i=0;i<15;i++)mesh(rear,new THREE.BoxGeometry(.64,.64,1.4),materials.metal(0xa59e74,{roughness:.5}),[x,8.25+(i-7)*2.54,16.6],'Core mating contact tail');
 for(const x of [-21,21])for(const y of [-12.75,29.25])screw(rear,[x,y,15.94],'back',1.35);
 rear.upperHarness=connector(rear,{name:'Upper 7P harness connector',position:[0,23.4,16.01],pins:7,pitch:1.25,width:11.2,height:3.4,color:0xbac5b5});
 const chips=materials.plastic(0x15201a,{roughness:.81}),termination=materials.metal(0x8c9688,{roughness:.55});
 for(const [name,x,y,w,h]of [['Left PCB IC',-8.6,19.9,3.1,3.8],['Right PCB IC',8.3,20.1,2.7,4.6]]){
  const chip=slab(rear,w,h,.6,.15,[x,y,16.01],chips,[],.05);chip.quaternion.copy(FACE.back);chip.name=name;
  for(const side of [-1,1])for(let n=0;n<4;n++)mesh(rear,new THREE.BoxGeometry(.55,.3,.17),termination,[x+side*(w/2+.14),y+(n-1.5)*.72,15.8],`${name} lead`);
 }
 for(const [x,y]of [[-13.1,21.4],[-13.1,18.8],[-12.4,16.2],[-8.6,15.6],[12.6,22.3],[12.6,19.7],[12.6,17.1],[8.4,16.3]]){
  const part=slab(rear,1.6,.75,.4,.1,[x,y,16.01],chips,[],.025);part.quaternion.copy(FACE.back);part.name='Rear PCB passive package';
  for(const side of [-1,1])mesh(rear,new THREE.BoxGeometry(.35,.78,.16),termination,[x+side*.63,y,15.75],'Rear PCB passive termination');
 }
 for(const x of [-11,11])for(let i=0;i<4;i++){
  mesh(rear,new THREE.BoxGeometry(.42,1.9,.42),termination,[x+(i-1.5)*2,29.36,13.15],`Head Grove ${x<0?'B':'C'} contact bend ${i+1}`);
  mesh(rear,new THREE.BoxGeometry(.42,.42,2.95),termination,[x+(i-1.5)*2,28.6,14.575],`Head Grove ${x<0?'B':'C'} PCB tail ${i+1}`);
 }
 rear.userData={role:'head-power-board',placementSource:'Official A180 front board / side photos, Core mating plane; board details photo-derived'};return rear;
}

function roundedRoute(points){
 const path=new THREE.CurvePath();let previous=points[0];
 for(let i=1;i<points.length-1;i++){
  const at=points[i],before=points[i-1],after=points[i+1],trim=Math.min(.9,at.distanceTo(before)*.3,at.distanceTo(after)*.3),enter=at.clone().lerp(before,trim/at.distanceTo(before)),leave=at.clone().lerp(after,trim/at.distanceTo(after));
  path.add(new THREE.LineCurve3(previous,enter));path.add(new THREE.QuadraticBezierCurve3(enter,at,leave));previous=leave;
 }
 path.add(new THREE.LineCurve3(previous,points.at(-1)));return path;
}

export function addNeckAdapter(host,mechanics){
 const adapter=new THREE.Group();adapter.name='Neck Adapter electronics';adapter.userData.role='yaw-adapter-board';host.body.add(adapter);
 const board=slab(adapter,24,19,.6,.8,[0,12.6,-17.8],materials.plastic(0x244736,{roughness:.9}),[],.03);board.quaternion.copy(FACE.top);board.name='Neck Adapter PCB';
 adapter.lowerHarness=connector(adapter,{name:'Lower 7P harness connector',position:[-1.3,14.9,-25],pins:7,pitch:1.25,width:11.2,height:3.4,color:0xbac5b5});
 adapter.servoConnectors=[];
 for(const side of [-1,1])adapter.servoConnectors.push(connector(adapter,{name:side<0?'Servo S1 connector':'Servo S2 connector',position:[side*8,13.2,-17.5],pins:3,pitch:2.54,width:7.8,height:3.9,color:0xc4ccc0,face:'top'}));
 host.root.updateMatrixWorld(true);
 const localPoint=o=>adapter.worldToLocal(o.getWorldPosition(new THREE.Vector3()));
 const colors=[0x121a16,0xa44832,0xb6beb2];adapter.servoLeads=[];
 for(const [which,servo]of [[0,mechanics.yawServo],[1,mechanics.pitchServo]])for(let i=0;i<3;i++){
  const start=localPoint(adapter.servoConnectors[which].contacts[i]),end=localPoint(servo.contacts[i]);
  const points=which===0?[start,new THREE.Vector3(-13,14.5,-26),new THREE.Vector3(-19.35,14,-26+(i-1)*.45),new THREE.Vector3(-19.35,1,-26+(i-1)*.45),new THREE.Vector3(-10,.6,-26),new THREE.Vector3(0,.6,-26),new THREE.Vector3(0,.6,-20),new THREE.Vector3(0,.6,end.z),end]:[start,new THREE.Vector3(13,15,-17.5+(i-1)*.6),new THREE.Vector3(14,13,-10),new THREE.Vector3(13,6.65,end.z),end];
  const curve=roundedRoute(points),wire=mesh(adapter,new THREE.TubeGeometry(curve,48,.18,7,false),materials.plastic(colors[i],{roughness:.8}),[0,0,0],`${which?'Pitch':'Yaw'} servo lead ${i+1}`);
  wire.userData={role:'servo-lead',startContact:adapter.servoConnectors[which].contacts[i].name,endContact:servo.contacts[i].name};adapter.servoLeads.push({wire,start:adapter.servoConnectors[which].contacts[i],end:servo.contacts[i]});
 }
 adapter.userData.placementSource='Official four-board schematic and rear loom photo; concealed adapter outline and servo lead routes inferred';return adapter;
}

export function addTopBoard(host){
 const top=new THREE.Group();top.name='Head top electronics';host.body.add(top);
 const pcb=materials.plastic(0x234331,{roughness:.88});
 // A separate Touch board follows the top cover. The narrow central carrier
 // stops before the CoreS3 back and leaves both Grove mouths unobstructed.
 const board=slab(top,47,37,.6,1.5,[0,33.3,-9.5],pcb,[],.06);board.quaternion.copy(FACE.top);board.name='Head Touch PCB';
 const carrier=slab(top,3.5,7.2,.6,.2,[0,33.3,11.6],pcb,[],.04);carrier.quaternion.copy(FACE.top);carrier.name='Top IR carrier PCB';
 const receiver=new THREE.Group();receiver.name='Top IR receiver assembly';receiver.position.set(0,34.52,10.25);receiver.quaternion.copy(FACE.top);top.add(receiver);
 mesh(receiver,new THREE.CylinderGeometry(1.22,1.35,.8,32).rotateX(Math.PI/2),materials.plastic(0x18211c,{roughness:.78}),[0,0,-.35],'Top IR receiver package');
 const lens=mesh(receiver,new THREE.SphereGeometry(1.2,32,20),materials.glossy(0x0d1712,{roughness:.18,clearcoat:.22}),[0,0,.25],'Top IR receiver lens');lens.scale.z=.45;
 return top;
}
