import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {FACE,mesh,slab,portQuaternion} from '../../modeling/parts.js';

/** Interior board with physical mounting bores and connector clearances. */
export function addBoard(host){
 const x=11.4,y=15.2,r=3.7,n=5.3,upper=8.3,s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-9);s.lineTo(n,-9);s.lineTo(n,-y);s.lineTo(x-r,-y);
 const angle=Math.acos((upper-(x-r))/r),cornerY=y-r+r*Math.sin(angle);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,angle);
 s.lineTo(upper,6.3);s.lineTo(-upper,6.3);s.lineTo(-upper,cornerY);
 s.absarc(-x+r,y-r,r,Math.PI-angle,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);
 for(const cx of [-8,8])s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy:-4,path:new THREE.Path(),clockwise:true}));
 s.holes.push(roundedRect(3.8,3.8,1.9,{cx:0,cy:-4,path:new THREE.Path(),clockwise:true}));
 const board=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:20}),materials.plastic(0x295343,{roughness:.91}),[0,0,-.5],'Weight-I2C PCB with open mounting bores');
 const packageMaterial=materials.plastic(0x23272a,{roughness:.78});
 // These packages live behind the real opaque covers; they are geometry,
 // rather than a photograph or a sheet placed across the connector mouths.
 for(const [name,w,h,x,y]of [['STM32 controller',4.5,6.5,3,4.5],['HX711 ADC',4,5,-3,7.5]])slab(host.body,w,h,.8,.2,[x,y,.3],packageMaterial,[],.04).name='Weight-I2C '+name;
 host.pcb=board;
}

export function addGrove(host,spec){
 const group=new THREE.Group();group.name='Weight-I2C open-top HY2.0-4P';group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const plastic=materials.plastic(spec.grove.color,{roughness:.6}),metal=materials.metal(0xb9ad82,{roughness:.43});
 const box=(size,pos,name,mat=plastic)=>mesh(group,new THREE.BoxGeometry(...size),mat,pos,'Weight-I2C Grove '+name);
 for(const x of [-4.65,4.65])box([.7,5.2,6.5],[x,0,-3.25],'side wall');
 for(const x of [-3.85,3.85])box([.9,.8,6.5],[x,2.2,-3.25],'upper rail');
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'rear wall');
 box([8.6,2.7,4.65],[0,-1.25,-4.175],'recessed contact support');
 box([3.4,.65,3],[0,1.2,-4.95],'short locking tongue');
 for(const x of [-4.65,4.65])box([.7,1.1,.6],[x,2.05,0],'mouth ear');
 for(let i=0;i<4;i++)box([.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],'contact '+(i+1),metal);
 group.userData={visualFamily:'open-top-grove',scope:'Appearance only; internal wall dimensions inferred from exact-product photographs.'};
 host.add(new Port({id:'grove',label:'HY2.0-4P · PORT.A I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'SCL'},{n:2,name:'SDA'},{n:3,name:'5V'},{n:4,name:'GND'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',i2cAddress:'0x26',scope:'Connector metadata only; no I2C or sensor behavior'}}));
 host.groveSocketAssembly={group};
}

export function addTerminal(host,spec){
 const group=new THREE.Group();group.name='Weight-I2C fixed HT3.96-4P socket';group.position.z=1.1;host.body.add(group);
 const orange=materials.plastic(0xf49b39,{roughness:.67}),metal=materials.metal(0xb9bcb3,{roughness:.42});
 slab(group,15.8,9.8,.6,.3,[0,11.1,-.8],orange,[],.06).name='Weight-I2C terminal floor';
 for(const x of [-7.55,7.55])slab(group,.7,9.8,6.4,.12,[x,11.1,-.2],orange,[],.04).name='Weight-I2C terminal side wall';
 slab(group,14.4,.7,5.8,.12,[0,6.35,-.2],orange,[],.035).name='Weight-I2C terminal rear wall';
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.25,r:.12,cx,cy:-3.65}));
 slab(group,15.8,9.8,.65,.3,[0,11.1,5.55],orange,windows,.06).name='Weight-I2C terminal roof with four inspection windows';
 for(const x of [-3.96,0,3.96])slab(group,.4,8.5,.7,.1,[x,11.7,-.2],orange,[],.035).name='Weight-I2C terminal channel rib';
 for(const x of spec.terminal.pinX){
  mesh(group,new THREE.BoxGeometry(.68,8.4,.68),metal,[x,10.9,1.3],'Weight-I2C terminal contact pin');
  mesh(group,new THREE.BoxGeometry(.68,1.9,.68),metal,[x,5.85,1.3],'Weight-I2C terminal bent lead');
  mesh(group,new THREE.BoxGeometry(.68,.68,2.4),metal,[x,4.9,-.1],'Weight-I2C terminal PCB tail');
 }
 for(const x of [-7,7])slab(group,.7,1.1,.4,.1,[x,15.45,5.8],orange,[],.035).name='Weight-I2C terminal retention ear';
 host.add(new Port({id:'terminal',label:'HT3.96-4P · Load-cell bridge',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,7],pins:spec.terminal.names.map((name,i)=>({n:spec.terminal.pinNumbers[i],name,signal:spec.terminal.signalNames[i]})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-1.4],order:col=>4-col},meta:{role:'visual-connector',face:'top',scope:'Physical connector only; no load-cell, wiring, excitation or conversion behavior'}}));
 host.terminalSocketAssembly={group};
}
