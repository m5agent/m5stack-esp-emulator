import * as THREE from 'three';
import {Port,Button,Led,materials} from '../../core/index.js';
import {mesh,slab,FACE,portQuaternion,screw} from '../../modeling/parts.js';
import {extractCadCap} from '../../modeling/actuators.js';
import {spec} from './dimensions.js';

export function addElectronics(host){
 const green=materials.plastic(0x254e3e,{roughness:.9}),dark=materials.plastic(0x242725,{roughness:.78});
 // Recessed solid PCB and component packages close the actual electronics
 // volume. They do not span the intentional corner mounting bores.
 host.pcb=slab(host.body,18,27.5,.8,1.2,[0,-.25,-6.4],green,[],.035);host.pcb.name='Mini Scales recessed PCB';
 for(const [name,w,h,x,y] of [['STM32',4.5,6.5,3,-2],['HX711',4,5,-3,-3]])slab(host.body,w,h,.9,.2,[x,y,-5.6],dark,[],.035).name='Mini Scales '+name+' package';
 for(const x of [-8,8])for(const y of [-8,10])screw(host.body,[x,y,1.05],'front',1.15);
}

export function addGrove(host){
 const group=new THREE.Group();group.name='Mini Scales open-top HY2.0-4P';group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const plastic=materials.plastic(spec.grove.color,{roughness:.6}),metal=materials.metal(0xb6aa82,{roughness:.44});
 const box=(size,pos,name,mat=plastic)=>mesh(group,new THREE.BoxGeometry(...size),mat,pos,'Mini Scales Grove '+name);
 for(const x of [-4.65,4.65])box([.7,5.2,6.5],[x,0,-3.25],'side wall');
 for(const x of [-3.85,3.85])box([.9,.8,6.5],[x,2.2,-3.25],'upper rail');
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'rear wall');
 box([8.6,2.7,4.65],[0,-1.25,-4.175],'contact support');box([3.4,.65,3],[0,1.2,-4.95],'short locking tongue');
 for(let i=0;i<4;i++)box([.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],'contact '+(i+1),metal);
 host.add(new Port({id:'grove',label:'HY2.0-4P · PORT.A I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,.6,5.2],pins:[{n:1,name:'SCL'},{n:2,name:'SDA'},{n:3,name:'5V'},{n:4,name:'GND'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',i2cAddress:'0x26',scope:'Connector metadata only; no I2C or sensor behavior'}}));
 host.groveSocketAssembly={group};
}

export function addControls(host){
 const {cap}=extractCadCap(host.parts['Mini Scales native inner carrier and button'],{name:'Mini Scales native RGB button cap',position:spec.button.position,face:'front',w:8.8,h:8.2,r:0,depth:13,outward:.02});
 host.functionButton=host.add(new Button({id:'button',label:'Mini Scales function button',mesh:cap,position:spec.button.position,travel:spec.button.travel,axis:spec.button.axis,meta:{role:'visual-control',visualMotion:'linear',travelEvidence:'0.18 mm appearance estimate at the real U177 function actuator; not a mechanical tolerance',scope:'Input intent only; no automatic tare, zeroing, power or RGB response'}}));
 // The real RGB light is at the same button end. Keep a recessed physical
 // lens in the native slot; an external framework alone sets its colour.
 const lens=new THREE.Mesh(new THREE.BoxGeometry(3.9,.35,.45),materials.plastic(0xd8ddd5,{roughness:.38}));lens.name='Mini Scales RGB recessed lens';
 host.rgbLight=host.add(new Led({id:'rgb',label:'Mini Scales external RGB',mesh:lens,position:[0,15.5,-1.25],radius:.3,glowSize:3,meta:{role:'externally-driven-visual',source:'Official U177 SK6812 indicator at RGB/BTN end; lens recess estimated from native CAD and photographs',scope:'No automatic indication, firmware or electrical behavior'}}));
}
