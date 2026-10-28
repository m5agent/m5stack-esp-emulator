// MIT. Exact own C124 shell, photograph-registered physical assembly. Hidden package/fit details are inferred.
import {Port,Led} from '../../core/index.js';
import {usbC} from '../../modeling/connectors.js';
import {THREE,materials,FACE,portQuaternion,mesh,box,plate,cylinder,annulus,ownNative} from './geometry.js';
import {NativeButton} from './NativeButton.js';
import native from './native-data.js';
import {DIM,spec} from './dimensions.js';
const mark=(o,family)=>{o.userData.visualFamily=family;return o;};
function group(host,name,p=[0,0,0],face){const g=new THREE.Group();g.name=name;g.position.fromArray(p);if(face)g.quaternion.copy(FACE[face]);host.body.add(g);return g;}
function header(host,{id,p,labels}){
 const n=labels.length,g=group(host,'C124 '+id+' physical female receiver',p,'back'),dark=materials.plastic(0x151a18,{roughness:.81}),inside=materials.plastic(0x222824,{roughness:.9}),gold=materials.metal(0xc4b686,{roughness:.43});
 const ys=labels.map((_,i)=>(n-1)/2*2.54-i*2.54),holes=ys.map(y=>({w:1.02,h:1.02,r:.055,y}));
 mark(plate(g,2.54,n*2.54-.2,2.2,[0,0,-2.2],dark,'C124 '+id+' bored closed molded housing',{radius:.04,holes}),'female-header-housing');
 for(let i=0;i<n;i++){
  const y=ys[i];mark(box(g,[1.02,1.02,.12],[0,y,-2.14],inside,'C124 '+id+' socket '+(i+1)+' recessed floor'),'header-socket-floor');
  for(const sign of [-1,1]){const contact=mark(box(g,[.12,.66,1.28],[sign*.34,y,-1.12],gold,'C124 '+id+' socket '+(i+1)+' spring contact'),'header-spring-contact');contact.userData.pin=i+1;}
  const tail=mark(cylinder(host.body,.15,2.0,[p[0],p[1]+y,-1.25],gold,'C124 '+id+' pin '+(i+1)+' through-PCB tail'),'header-tail');tail.userData.pin=i+1;
 }
 host.add(new Port({id,label:'C124 '+n+'-pin female expansion',connector:'m5.atom.ext-'+n+'p',position:p,quaternion:portQuaternion('back'),hitSize:[2.82,1,n*2.54+.1],pins:labels.map((name,i)=>({n:i+1,name,signal:name})),pinGrid:{cols:1,rows:n,pitch:2.54,center:[0,0],order:(_c,r)=>n-r},meta:{face:'back',role:'visual-connector',gender:'female',scope:'Mechanical family and documented pin labels only;no bus/electrical compatibility simulation'}}));
 return g;
}
function grove(host){
 const g=group(host,'C124 actual HY2.0-4P receiver',DIM.grove,'bottom'),white=materials.plastic(0xe6e9df,{roughness:.66}),metal=materials.metal(0xc0b487,{roughness:.42});
 mark(plate(g,10.8,3.5,6.25,[0,0,-6.25],white,'C124 Grove keyed molded walls',{radius:.22,holes:[{w:8.7,h:2.65,r:.15}]}),'grove-receiver');
 mark(box(g,[8.68,2.64,.5],[0,0,-6.0],white,'C124 Grove physical dielectric rear wall'),'grove-rear-wall');
 for(const x of [-4.4,4.4])box(g,[.65,.58,1.3],[x,1.1,-.5],white,'C124 Grove latch/retaining rail');
 const contacts=[];
 for(let i=0;i<4;i++){
  const x=(i-1.5)*2,pin=mark(box(g,[.4,.4,4.7],[x,-.2,-3.4],metal,'C124 Grove contact '+(i+1)),'grove-contact');pin.userData.pin=i+1;contacts.push(pin);
  mark(box(g,[.4,.4,1.05],[x,-.2,-6.55],metal,'C124 Grove rear contact tail '+(i+1)),'grove-tail');
  mark(cylinder(host.body,.17,2.45,[x,-5.48,-1.93],metal,'C124 Grove pin '+(i+1)+' raised solder return'),'grove-tail');
  annulus(host.body,.38,.25,.055,[x,-5.48,-.218],metal,'C124 Grove through-PCB solder pad '+(i+1));
 }
 for(const x of [-5.0,5.0])box(host.body,[.45,1.3,1.0],[x,-7.1,-1.63],materials.metal(0xaeb5b0,{roughness:.5}),'C124 Grove board retention foot');
 host.add(new Port({id:'grove',label:'C124 HY2.0-4P · GND/5V/G2/G1',connector:'grove',position:DIM.grove,quaternion:portQuaternion('bottom'),hitSize:[10.8,1,3.5],pins:spec.grovePins.map((name,i)=>({n:i+1,name,signal:name})),meta:{face:'bottom',role:'visual-connector',scope:'Four-contact mechanical mating frame only;no I2C/UART/power simulation'}}));
 return {group:g,contacts};
}
export function buildAssembly(host){
 const parts=ownNative(host,native),a={parts};host.atomS3LiteAssembly=a;
 const board=materials.plastic(0x244b3d,{roughness:.9}),metal=materials.metal(0xb5bcb3,{roughness:.47}),gold=materials.metal(0xb5a477,{roughness:.48}),dark=materials.plastic(0x1d2722,{roughness:.81}),white=materials.plastic(0xe7e9e1,{roughness:.68});
 const holes=[{radius:2.0,x:0,y:-.1}];
 for(const [p,labels]of [[DIM.header5,spec.header5Pins],[DIM.header4,spec.header4Pins]])for(let i=0;i<labels.length;i++)holes.push({radius:.29,x:p[0],y:p[1]+(labels.length-1)/2*2.54-i*2.54-.1});
 for(const x of [-3,-1,1,3])holes.push({radius:.26,x,y:-5.58});
 for(const [x,y]of [[-8.2,7],[8.2,7],[-4.6,-3.5],[4.6,-3.5]])holes.push({radius:.3,x,y:y-.1});
 a.pcb=mark(plate(host.body,20,19.4,.8,[-0,.1,-1.05],board,'C124 ESP32-S3FN8 main PCB actual thickness',{radius:.85,holes}),'main-pcb');
 // A thick mechanically retained rear carrier supports the exposed receiver banks;
 // its open-bottom Grove notch and bank/mount holes remain real through openings.
 const profile=new THREE.Shape();profile.moveTo(-9,-9.3);profile.lineTo(-5.46,-9.3);profile.lineTo(-5.46,-5.4);profile.lineTo(5.46,-5.4);profile.lineTo(5.46,-9.3);profile.lineTo(9,-9.3);profile.absarc(9,-8.7,.6,-Math.PI/2,0,false);profile.lineTo(9.6,8.7);profile.absarc(9,8.7,.6,0,Math.PI/2,false);profile.lineTo(-9,9.3);profile.absarc(-9,8.7,.6,Math.PI/2,Math.PI,false);profile.lineTo(-9.6,-8.7);profile.absarc(-9,-8.7,.6,Math.PI,Math.PI*1.5,false);profile.closePath();
 const mountHole=new THREE.Path();mountHole.absarc(0,0,3.2,0,Math.PI*2,true);profile.holes.push(mountHole);
 for(const [pos,count]of [[DIM.header5,5],[DIM.header4,4]]){const w=2.62,h=count*2.54-.12,x=pos[0],y=pos[1],cut=new THREE.Path();cut.moveTo(x-w/2,y-h/2);cut.lineTo(x-w/2,y+h/2);cut.lineTo(x+w/2,y+h/2);cut.lineTo(x+w/2,y-h/2);cut.closePath();profile.holes.push(cut);}
 a.rearCarrier=mark(mesh(host.body,new THREE.ExtrudeGeometry(profile,{depth:.55,bevelEnabled:false,curveSegments:24}),white,[0,0,-3.4],'C124 thick rear receiver/PCB retaining carrier'),'rear-retaining-carrier');

 for(const [x,y]of [[-8.2,7],[8.2,7],[-4.6,-3.5],[4.6,-3.5]]){const post=annulus(host.body,.53,.27,1.67,[x,y,-2.83],white,'C124 PCB retaining standoff');post.userData.visualFamily='pcb-support';cylinder(host.body,.26,.28,[x,y,-1.05],metal,'C124 PCB retaining fastener');}
 a.m2Floor=cylinder(host.body,1.12,.22,[0,0,-1.83],white,'C124 M2 blind mounting physical stop');a.m2Floor.userData.visualFamily='mounting-stop';
 // Rear native platform already has the real M2 bore walls; the stop is recessed.
 a.usb=usbC(host,{id:'usb',position:DIM.usb,face:'bottom',w:8.65,h:3.05,depth:4.85});a.usb.name='C124 complete USB-C receptacle';
 for(const x of [-4.22,4.22]){box(host.body,[.36,2.0,1.25],[x,-8.8,.25],metal,'C124 USB-C metal board retention');box(host.body,[.8,.8,.12],[x,-7.65,-.18],metal,'C124 USB-C soldered retention foot');}
 for(let i=0;i<12;i++)box(host.body,[.18,.8,.08],[(i-5.5)*.5,-6.92,-.18],gold,'C124 USB-C rear solder termination');
 a.grove=grove(host);
 a.groveRearSupport=box(host.body,[10.7,.78,.6],[0,-5.36,-4.2],white,'C124 Grove rear dielectric carrier support');
 a.header5=header(host,{id:'ext-5p',p:DIM.header5,labels:spec.header5Pins});a.header4=header(host,{id:'ext-4p',p:DIM.header4,labels:spec.header4Pins});
 a.soc=box(host.body,[7.0,7.0,.72],[2,4,.16],dark,'C124 ESP32-S3FN8 package inferred placement');
 for(let i=0;i<8;i++)for(const side of [-1,1])box(host.body,[.35,.12,.08],[2+side*3.54,1.0+i*.82,-.16],gold,'C124 SoC solder terminal');
 box(host.body,[3.5,2.2,1.35],[6.5,8.0,.425],white,'C124 own 3D antenna package inferred placement');
 for(const [x,y]of [[-5,5],[-5.5,7],[-4,7],[-3.5,3],[-6,0],[5,-2]]){box(host.body,[1.25,.75,.48],[x,y,-.01],materials.plastic(0xa9a184,{roughness:.83}),'C124 regulator/passive visual envelope');for(const d of [-.7,.7])box(host.body,[.2,.75,.12],[x+d,y,-.18],metal,'C124 passive solder termination');}
 const mainSwitch=box(host.body,[3.5,3.4,1.35],[0,-2,.425],dark,'C124 G41 PCB mounted switch body');a.mainSwitch=mainSwitch;
 for(const x of [-1.7,1.7])for(const y of [-3.4,-.6])box(host.body,[.55,.55,.18],[x,y,-.16],metal,'C124 G41 switch mounting terminal');
 a.mainPlunger=cylinder(host.body,.75,1.9,[0,-2,2.22],white,'C124 G41 switch real moving plunger');
 a.resetSwitch=box(host.body,[2.4,3.0,.9],[-8.0,4.5,.2],dark,'C124 separate side Reset PCB switch body');
 a.resetPlunger=cylinder(host.body,.48,.4,[-9.03,4.5,.2],white,'C124 Reset inward moving switch head','x');
 // The fixed emitter is below the flexing native slit. A small optical guide follows only the cap.
 a.rgbSupport=plate(host.body,3.2,3.2,.25,[0,0,2.1],board,'C124 RGB daughter carrier supported above PCB',{radius:.2});
 for(const x of [-1.25,1.25])cylinder(host.body,.23,2.34,[x,0,.92],metal,'C124 RGB carrier solder/support post');
 a.rgbPackage=box(host.body,[2.0,2.0,.8],[0,0,2.75],white,'C124 one WS2812C-2020 body');
 for(const x of [-.9,.9])for(const y of [-.7,.7])box(host.body,[.35,.45,.13],[x,y,2.3],metal,'C124 RGB package solder pad');
 const optic=box(host.body,[2.4,.12,1.0],[0,0,4.05],materials.plastic(0xe0e5dc,{roughness:.43,clearcoat:.23}),'C124 narrow RGB slit physical optical guide');
 const rgb=host.add(new Led({id:'rgb',label:'C124 RGB · G35',mesh:optic,radius:0,glowSize:1.6,meta:{gpio:'G35',emitter:'WS2812C-2020',count:1,role:'externally-driven-visual',scope:'External visible color/brightness only;not boot/reset/download status'}}));rgb.glow.position.set(0,0,4.62);a.rgb=rgb;
 // Native optical notch at own x≈-7,y=+12,z≈2.2. No visible Led component is created for IR.
 const ir=group(host,'C124 passive G4 IR emitter assembly');a.ir=ir;
 plate(ir,2.4,1.8,.24,[-7.05,8.9,1.03],board,'C124 IR support daughter PCB',{radius:.16});
 for(const x of [-7.55,-6.55]){cylinder(ir,.15,1.42,[x,9.25,.42],metal,'C124 IR actual solder/support lead');box(ir,[.25,.6,.22],[x,9.78,1.1],metal,'C124 IR bent terminal');}
 cylinder(ir,.35,1.02,[-7.05,10.85,1.85],dark,'C124 passive IR dark resin package','y');
 const irLens=mesh(ir,new THREE.SphereGeometry(.35,24,16),materials.glossy(0x29362a,{roughness:.28}),[-7.05,11.32,1.85],'C124 passive IR optical dome');irLens.scale.y=.7;
 const button=host.add(new NativeButton(parts['upper-shell'],{id:'button',label:'C124 G41 top U-tongue',face:'front',position:[0,1.1,4.76],travel:spec.travelMm.button,gpio:'G41'}));
 const reset=host.add(new NativeButton(parts['lower-shell'],{id:'reset',label:'C124 separate side Reset',face:'left',position:[-11.03,4.5,-.1],travel:spec.travelMm.reset,gpio:'RESET'}));
 button.follow(a.mainPlunger,[0,0,-1],button.weightAt(-2,3));button.follow(rgb.lens,[0,0,-1],button.weightAt(0,4));button.follow(rgb.glow,[0,0,-1],button.weightAt(0,4));reset.follow(a.resetPlunger,[1,0,0],reset.weightAt(4.5,.2));a.button=button;a.reset=reset;
 return a;
}
