// MIT. Original C126-CAM own native enclosure plus photograph-registered physical internals.
// Hidden package, support and travel dimensions are appearance inferences, not manufacturing CAD.
import {Port,Led} from '../../core/index.js';
import {usbC} from '../../modeling/connectors.js';
import {THREE,materials,FACE,portQuaternion,mesh,box,plate,cylinder,annulus,ownNative} from './geometry.js';
import {NativeReset} from './NativeReset.js';
import native from './native-data.js';
import {DIM,spec} from './dimensions.js';
const mark=(o,family)=>{o.userData.visualFamily=family;return o;};
function group(host,name,p=[0,0,0],face){const g=new THREE.Group();g.name=name;g.position.fromArray(p);if(face)g.quaternion.copy(FACE[face]);host.body.add(g);return g;}
function header(host,id,p,labels){
 const n=labels.length,g=group(host,'C126-CAM '+id+' physical female receiver',p,'back'),dark=materials.plastic(0x141b17,{roughness:.81}),gold=materials.metal(0xc4b586,{roughness:.43}),ys=labels.map((_,i)=>(n-1)/2*2.54-i*2.54),holes=ys.map(y=>({w:1.02,h:1.02,r:.055,y}));
 mark(plate(g,2.54,n*2.54-.2,2.2,[0,0,-2.2],dark,'C126-CAM '+id+' bored closed molded housing',{radius:.04,holes}),'female-header-housing');
 for(let i=0;i<n;i++){const y=ys[i];mark(box(g,[1.02,1.02,.12],[0,y,-2.14],dark,'C126-CAM '+id+' socket '+(i+1)+' recessed floor'),'header-socket-floor');for(const sign of [-1,1]){const c=mark(box(g,[.12,.66,1.28],[sign*.34,y,-1.12],gold,'C126-CAM '+id+' socket '+(i+1)+' actual spring contact'),'header-spring-contact');c.userData.pin=i+1;}mark(cylinder(host.body,.15,3.4,[p[0],p[1]+y,-2.4],gold,'C126-CAM '+id+' pin '+(i+1)+' solder tail'),'header-tail');}
 host.add(new Port({id,label:'C126-CAM '+n+'-pin female expansion',connector:'m5.atom.ext-'+n+'p',position:p,quaternion:portQuaternion('back'),hitSize:[2.82,1,n*2.54+.1],pins:labels.map((name,i)=>({n:i+1,name,signal:name})),pinGrid:{cols:1,rows:n,pitch:2.54,center:[0,0],order:(_c,r)=>n-r},meta:{face:'back',role:'visual-connector',gender:'female',scope:'Documented labels and mechanical frame only;no electrical or protocol simulation'}}));return g;
}
function grove(host){
 const g=group(host,'C126-CAM HY2.0-4P complete receiver',DIM.grove,'bottom'),white=materials.plastic(0xe6e9df,{roughness:.66}),metal=materials.metal(0xc0b487,{roughness:.42});
 mark(plate(g,10.8,3.5,6.25,[0,0,-6.25],white,'C126-CAM Grove keyed molded walls',{radius:.22,holes:[{w:8.7,h:2.65,r:.15}]}),'grove-receiver');mark(box(g,[8.68,2.64,.5],[0,0,-6],white,'C126-CAM Grove physical dielectric rear wall'),'grove-rear-wall');
 for(const x of [-4.4,4.4])box(g,[.65,.58,1.3],[x,1.1,-.5],white,'C126-CAM Grove actual latch rail');
 const contacts=[];for(let i=0;i<4;i++){const x=(i-1.5)*2,c=mark(box(g,[.4,.4,4.7],[x,-.2,-3.4],metal,'C126-CAM Grove contact '+(i+1)),'grove-contact');c.userData.pin=i+1;contacts.push(c);mark(box(g,[.4,.4,1.1],[x,-.2,-6.55],metal,'C126-CAM Grove rear tail '+(i+1)),'grove-tail');cylinder(host.body,.17,2.4,[x,-5.47,-2.15],metal,'C126-CAM Grove PCB solder return');}
 for(const x of [-5,5])box(host.body,[.45,1.3,1.2],[x,-7,-2.9],metal,'C126-CAM Grove retention foot');
 host.add(new Port({id:'grove',label:'C126-CAM HY2.0-4P · GND/5V/G2/G1',connector:'grove',position:DIM.grove,quaternion:portQuaternion('bottom'),hitSize:[10.8,1,3.5],pins:spec.grovePins.map((name,i)=>({n:i+1,name,signal:name})),meta:{face:'bottom',role:'visual-connector',scope:'Four-wire mechanical connection only;no I2C/UART/power simulation'}}));return {group:g,contacts};
}
export function buildAssembly(host){
 const actualHost=host,parts=ownNative(host,native),a={parts};const base=new THREE.Group();base.name='C126-CAM physical main-board assembly';base.position.z=.45;actualHost.body.add(base);a.base=base;host={body:base,add:c=>actualHost.add(c,base),options:actualHost.options};actualHost.atomS3RCamAssembly=a;
 const board=materials.plastic(0x244b3d,{roughness:.9}),metal=materials.metal(0xb5bcb3,{roughness:.47}),gold=materials.metal(0xc4b487,{roughness:.45}),dark=materials.plastic(0x18221d,{roughness:.83}),white=materials.plastic(0xe7e9e1,{roughness:.68});
 const headerBores=[];for(const [p,labels]of [[DIM.header5,spec.header5Pins],[DIM.header4,spec.header4Pins]])for(let i=0;i<labels.length;i++)headerBores.push({radius:.29,x:p[0],y:p[1]+(labels.length-1)/2*2.54-i*2.54});
 const supportPoints=[[-8.3,8],[8.3,8],[-6,-4.6],[6,-4.6]],mounts=supportPoints.map(([x,y])=>({radius:.3,x,y}));
 a.pcb=mark(plate(host.body,20,20,.8,[0,0,-1.05],board,'C126-CAM ESP32-S3-PICO-1-N8R8 main PCB actual thickness',{radius:1.05,holes:[{radius:1.85,x:0,y:0},...headerBores,...mounts]}),'main-pcb');
 const rearOutline=new THREE.Shape();rearOutline.moveTo(-8.5,-9.7);rearOutline.lineTo(-5.45,-9.7);rearOutline.lineTo(-5.45,-5.4);rearOutline.lineTo(5.45,-5.4);rearOutline.lineTo(5.45,-9.7);rearOutline.lineTo(8.5,-9.7);rearOutline.absarc(8.5,-8.5,1.2,-Math.PI/2,0,false);rearOutline.lineTo(9.7,8.5);rearOutline.absarc(8.5,8.5,1.2,0,Math.PI/2,false);rearOutline.lineTo(-8.5,9.7);rearOutline.absarc(-8.5,8.5,1.2,Math.PI/2,Math.PI,false);rearOutline.lineTo(-9.7,-8.5);rearOutline.absarc(-8.5,-8.5,1.2,Math.PI,Math.PI*1.5,false);rearOutline.closePath();
 for(const [p,n]of [[DIM.header5,5],[DIM.header4,4]]){const cut=new THREE.Path(),x=p[0],y=p[1],w=2.62,h=n*2.54-.12;cut.moveTo(x-w/2,y-h/2);cut.lineTo(x-w/2,y+h/2);cut.lineTo(x+w/2,y+h/2);cut.lineTo(x+w/2,y-h/2);cut.closePath();rearOutline.holes.push(cut);}
 const bore=new THREE.Path();bore.absarc(0,0,3.2,0,Math.PI*2,true);rearOutline.holes.push(bore);
 a.rearCarrier=mark(mesh(host.body,new THREE.ExtrudeGeometry(rearOutline,{depth:.45,bevelEnabled:false,curveSegments:24}),white,[0,0,-5.15],'C126-CAM rear physical receiver retaining carrier'),'rear-retaining-carrier');
 a.imuBoard=mark(plate(host.body,11,13,.65,[0,3,-4.55],board,'C126-CAM BMI270 and BMM150 daughter PCB actual thickness',{radius:.65,holes:[{radius:3.2,x:0,y:-3}]}),'imu-pcb');
 box(host.body,[2.5,3,.8],[0,5.5,-3.5],dark,'C126-CAM BMI270 package visual envelope');box(host.body,[1.6,1.6,.6],[3,5.5,-3.6],dark,'C126-CAM BMM150 package visual envelope');
 for(const [x,y]of supportPoints){annulus(host.body,.55,.28,3.22,[x,y,-4.55],white,'C126-CAM actual PCB retaining standoff');cylinder(host.body,.27,.2,[x,y,-.23],metal,'C126-CAM PCB retaining fastener');}
 a.m2Tube=annulus(host.body,1.63,1.10,3.1,[0,0,-6.2],white,'C126-CAM real M2 blind mounting tube');a.m2Floor=mark(cylinder(host.body,1.10,.2,[0,0,-3],white,'C126-CAM M2 actual deep blind mounting stop'),'mounting-stop');
 a.usb=usbC(host,{id:'usb',position:DIM.usb,face:'bottom',w:8.65,h:3.05,depth:4.85});a.usb.name='C126-CAM complete USB-C receptacle';
 // The own shell has a broad assembly window; this is the real connector/PCB
 // assembly and its insulating surround, never a painted black closure plane.
 const usbSeat=group(host,'C126-CAM USB-C rectangular dielectric package seat',DIM.usb,'bottom');plate(usbSeat,9.7,3.7,4.75,[0,0,-4.75],dark,'C126-CAM USB-C bored rectangular package surround',{radius:.4,holes:[{w:8.75,h:3.15,r:1.575}]});
 for(const x of [-4.5,4.5])box(host.body,[.36,2,1.3],[x,-8.5,1.1],metal,'C126-CAM USB-C actual metal retention');for(let i=0;i<12;i++)box(host.body,[.18,.8,.08],[(i-5.5)*.5,-6.92,.55],gold,'C126-CAM USB-C rear solder termination');
 a.grove=grove(host);a.header5=header(host,'ext-5p',DIM.header5,spec.header5Pins);a.header4=header(host,'ext-4p',DIM.header4,spec.header4Pins);
 for(const side of [-1,1]){box(host.body,[.8,3.3,3.7],[side*5.85,-8.45,-2.75],dark,'C126-CAM Grove socket side insulating seat');box(host.body,[.35,1.5,2.5],[side*5.3,-10.7,-2.7],metal,'C126-CAM Grove retaining clip');}
 box(host.body,[7,7,.8],[2.4,4.5,.18],dark,'C126-CAM ESP32-S3-PICO-1-N8R8 package inferred envelope');box(host.body,[3.5,2.2,1.2],[6.2,8,.37],white,'C126-CAM own PROANT440 antenna inferred placement');
 for(const [x,y]of [[-5,5],[-5.4,7],[-4,7],[-5,-1],[6,-2]]){box(host.body,[1.25,.75,.48],[x,y,-.01],materials.plastic(0xa9a184,{roughness:.83}),'C126-CAM regulator/passive envelope');for(const d of [-.7,.7])box(host.body,[.2,.75,.12],[x+d,y,-.18],metal,'C126-CAM passive solder termination');}
 const resetHousing=group(host,'C126-CAM separate Reset board switch housing',[-9.6,4.5,-2],'left');a.resetSwitch=plate(resetHousing,3,1.4,1.5,[0,0,-1.5],dark,'C126-CAM Reset real bored switch body',{radius:.12,holes:[{radius:.50,x:0,y:0}]});a.resetPlunger=cylinder(host.body,.48,.35,[-9.82,4.5,-2],white,'C126-CAM actual side Reset moving head','x');
 // Passive IR stays a dark physical optic, independent of display commands.
 const ir=group(host,'C126-CAM G47 passive IR assembly');a.ir=ir;plate(ir,1.8,1.6,.20,[-7,9.2,-.15],board,'C126-CAM IR daughter support',{radius:.15});for(const x of [-7.35,-6.65])box(ir,[.15,1.2,.20],[x,10,.2],metal,'C126-CAM IR support/solder lead');cylinder(ir,.25,1.0,[-7,10.85,.2],dark,'C126-CAM IR resin package','y');a.irLens=mesh(ir,new THREE.SphereGeometry(.25,24,16),materials.glossy(0x1b251f,{roughness:.29}),[-7,11.35,.2],'C126-CAM passive IR optical dome');a.irLens.scale.y=.7;
 // Actual C126-CAM fixed camera carrier, sensor, optical stack and cover glass.
 const camera=group(host,'C126-CAM camera daughter assembly');a.camera=camera;
 a.cameraBoard=plate(camera,17,17,.65,[0,0,2.55],board,'C126-CAM actual camera PCB with sensor support',{radius:.65});
 for(const [x,y]of [[-6,-6],[6,-6],[-6,6],[6,6]])cylinder(camera,.7,1.4,[x,y,1.85],white,'C126-CAM camera carrier support');
 a.cameraSensor=box(camera,[5.7,5.7,1.0],[0,0,3.7],dark,'C126-CAM GC0308 actual sensor package envelope');
 a.cameraBarrel=annulus(camera,2.3,1.05,2.1,[0,0,4.2],dark,'C126-CAM actual lens barrel with through optical bore');
 a.opticalStop=cylinder(camera,1.0,.18,[0,0,4.25],materials.glossy(0x17342c,{roughness:.12}),'C126-CAM deep physical sensor/IR-cut optical substrate');
 a.cameraLens=mesh(camera,new THREE.SphereGeometry(1.03,32,24),new THREE.MeshPhysicalMaterial({color:0x304d43,roughness:.09,metalness:.08,clearcoat:.9}),[0,0,5.65],'C126-CAM actual recessed front lens');a.cameraLens.scale.z=.27;
 // Whole glass disc has thickness; black mask/orange annotation are separate ink.
 a.cameraGlass=cylinder(camera,9.7,.18,[0,0,6.53],new THREE.MeshPhysicalMaterial({color:0xdce6e1,roughness:.12,metalness:0,transparent:true,opacity:.16,transmission:.25,ior:1.5,depthWrite:false}),'C126-CAM actual thick protective camera glass');
 const lamp=box(host.body,[1.0,1.0,.45],[-9,-9,5.05],white,'C126-CAM G18 indicator LED physical package');a.indicatorPackage=lamp;
 const lens=cylinder(host.body,.35,1.8,[-9,-9,6.13],materials.plastic(0xdce0d6,{roughness:.42}),'C126-CAM actual recessed indicator optical guide');
 a.indicator=host.add(new Led({id:'camera-led',label:'C126-CAM camera indicator · G18',mesh:lens,radius:0,glowSize:1.2,meta:{gpio:'G18',role:'externally-driven-visual',nominalColor:'white',scope:'External visible indicator only;no camera power/boot state emulation'}}));a.indicator.glow.position.set(-9,-9,7.15);
 a.reset=actualHost.add(new NativeReset(parts['lower-shell']));a.reset.follow(a.resetPlunger);
 a.ir.position.z+=.30;
 return a;
}
