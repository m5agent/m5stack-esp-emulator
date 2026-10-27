import*as THREE from'three';import{Port,materials}from'../../core/index.js';import{mesh,FACE,portQuaternion}from'../../modeling/parts.js';import{spec}from'./dimensions.js';
export function grove(host){
 const group=new THREE.Group();group.name='RS485-ISO open-top HY2.0-4P';group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const plastic=materials.plastic(spec.grove.color,{roughness:.65}),metal=materials.metal(0xb6aa82,{roughness:.42}),box=(size,p,name,mat=plastic)=>mesh(group,new THREE.BoxGeometry(...size),mat,p,'RS485-ISO Grove '+name);
 for(const sign of[-1,1]){box([.65,5.2,6.5],[sign*4.675,0,-3.25],'side wall');box([.7,.6,3],[sign*3.85,2.3,-4.9],'guide rail');box([.65,.6,1.1],[sign*3.7,2.3,-1.2],'latch shoulder');}
 box([8.7,.65,6.5],[0,-2.275,-3.25],'floor');box([8.7,4.55,.65],[0,.325,-6.175],'rear wall');box([4.8,.45,2.1],[0,2.375,-4.65],'locking bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.6],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal);box([.42,1.2,.42],[(i-1.5)*2,-1.6,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART RX/TX',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical attachment/cable pose only; no UART,RS485 transceiver,bus,supply,isolation or firmware behavior'}}));return{group,port};
}
export function terminal(host){
 const frame=new THREE.Group();frame.name='RS485-ISO fixed four-pole VH3.96 socket';frame.position.fromArray(spec.terminal.position);host.body.add(frame);
 const orange=materials.plastic(0xf38e2e,{roughness:.67}),metal=materials.metal(0xb5b6a1,{roughness:.42}),box=(size,p,name,mat=orange)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'RS485-ISO fixed terminal '+name);
 const rear=box([16,.7,7],[0,-9.65,0],'rear support');
 for(const side of[-1,1])box([.65,9.3,7],[side*7.675,-4.65,0],'side cheek');
 box([14.7,9.3,.55],[0,-4.65,-3.225],'lower retention wall');
 box([14.7,6.95,.55],[0,-3.475,3.225],'upper forward retention wall');
 box([14.7,.85,.55],[0,-8.875,3.225],'upper rear retention wall');
 for(const x of spec.terminal.pinX){box([.62,7.2,.62],[x,-4.6,-.4],'contact pin',metal);box([.62,.62,3],[x,-9.65,-1.9],'PCB tail',metal);}
 // The visible moulded lip/latch apertures on the upper cover are solids around real slots.
 for(const x of[-7.5,-3.96,0,3.96,7.5])box([.65,1.5,.55],[x,-7.7,3.225],'upper latch partition');
 box([16,.5,.55],[0,-8.45,3.225],'upper latch rear rib');
 const port=host.add(new Port({id:'terminal',label:'RS485-ISO · VH3.96-4P',connector:'vh3.96-4p',position:spec.terminal.position,hitSize:[16,1,7],pins:spec.terminal.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-.4],order:col=>col+1},meta:{role:'visual-connector',face:'top',scope:'Physical connector and attachment frame only; no bus continuity, termination, isolation, electrical or firmware state',terminalOrderEvidence:'Exact U094 front photograph reads B/A/crossed NC/G; own v1.1 JP1 maps pin4 B,pin3 A,pin2 NC,pin1 SHIELD. Port n indexes front-view physical slot order,not schematic pin number. G denotes isolated SHIELD,not HOST_GND,no supply terminal.'}}));return{frame,rear,port};
}
