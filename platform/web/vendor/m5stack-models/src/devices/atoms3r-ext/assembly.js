// MIT. Original C126-Ext own native enclosure plus photograph-registered physical internals.
// Hidden package, support and travel dimensions are appearance inferences, not manufacturing CAD.
import {Port} from '../../core/index.js';
import {usbC} from '../../modeling/connectors.js';
import {THREE,materials,FACE,portQuaternion,mesh,box,plate,cylinder,annulus,ownNative} from './geometry.js';
import {NativeReset} from './NativeReset.js';
import native from './native-data.js';
import {DIM,spec} from './dimensions.js';
const mark=(o,family)=>{o.userData.visualFamily=family;return o;};
function group(host,name,p=[0,0,0],face){const g=new THREE.Group();g.name=name;g.position.fromArray(p);if(face)g.quaternion.copy(FACE[face]);host.body.add(g);return g;}
function header(host,id,p,labels){
 const n=labels.length,g=group(host,'C126-Ext '+id+' physical female receiver',p,'back'),dark=materials.plastic(0x141b17,{roughness:.81}),gold=materials.metal(0xc4b586,{roughness:.43}),ys=labels.map((_,i)=>(n-1)/2*2.54-i*2.54),holes=ys.map(y=>({w:1.02,h:1.02,r:.055,y}));
 mark(plate(g,2.54,n*2.54-.2,2.2,[0,0,-2.2],dark,'C126-Ext '+id+' bored closed molded housing',{radius:.04,holes}),'female-header-housing');
 for(let i=0;i<n;i++){const y=ys[i];mark(box(g,[1.02,1.02,.12],[0,y,-2.14],dark,'C126-Ext '+id+' socket '+(i+1)+' recessed floor'),'header-socket-floor');for(const sign of [-1,1]){const c=mark(box(g,[.12,.66,1.28],[sign*.34,y,-1.12],gold,'C126-Ext '+id+' socket '+(i+1)+' actual spring contact'),'header-spring-contact');c.userData.pin=i+1;}mark(cylinder(host.body,.15,3.4,[p[0],p[1]+y,-2.4],gold,'C126-Ext '+id+' pin '+(i+1)+' solder tail'),'header-tail');}
 host.add(new Port({id,label:'C126-Ext '+n+'-pin female expansion',connector:'m5.atom.ext-'+n+'p',position:p,quaternion:portQuaternion('back'),hitSize:[2.82,1,n*2.54+.1],pins:labels.map((name,i)=>({n:i+1,name,signal:name})),pinGrid:{cols:1,rows:n,pitch:2.54,center:[0,0],order:(_c,r)=>n-r},meta:{face:'back',role:'visual-connector',gender:'female',scope:'Documented labels and mechanical frame only;no electrical or protocol simulation'}}));return g;
}
function grove(host){
 const g=group(host,'C126-Ext HY2.0-4P complete receiver',DIM.grove,'bottom'),white=materials.plastic(0xe6e9df,{roughness:.66}),metal=materials.metal(0xc0b487,{roughness:.42});
 mark(plate(g,10.8,3.5,6.25,[0,0,-6.25],white,'C126-Ext Grove keyed molded walls',{radius:.22,holes:[{w:8.7,h:2.65,r:.15}]}),'grove-receiver');mark(box(g,[8.68,2.64,.5],[0,0,-6],white,'C126-Ext Grove physical dielectric rear wall'),'grove-rear-wall');
 for(const x of [-4.4,4.4])box(g,[.65,.58,1.3],[x,1.1,-.5],white,'C126-Ext Grove actual latch rail');
 const contacts=[];for(let i=0;i<4;i++){const x=(i-1.5)*2,c=mark(box(g,[.4,.4,4.7],[x,-.2,-3.4],metal,'C126-Ext Grove contact '+(i+1)),'grove-contact');c.userData.pin=i+1;contacts.push(c);mark(box(g,[.4,.4,1.1],[x,-.2,-6.55],metal,'C126-Ext Grove rear tail '+(i+1)),'grove-tail');cylinder(host.body,.17,2.4,[x,-5.47,-2.15],metal,'C126-Ext Grove PCB solder return');}
 for(const x of [-5,5])box(host.body,[.45,1.3,1.2],[x,-7,-2.9],metal,'C126-Ext Grove retention foot');
 host.add(new Port({id:'grove',label:'C126-Ext HY2.0-4P · GND/5V/G2/G1',connector:'grove',position:DIM.grove,quaternion:portQuaternion('bottom'),hitSize:[10.8,1,3.5],pins:spec.grovePins.map((name,i)=>({n:i+1,name,signal:name})),meta:{face:'bottom',role:'visual-connector',scope:'Four-wire mechanical connection only;no I2C/UART/power simulation'}}));return {group:g,contacts};
}
export function buildAssembly(host){
 const actualHost=host,parts=ownNative(host,native),a={parts};const base=new THREE.Group();base.name='C126-Ext physical main-board assembly';base.position.z=.45;actualHost.body.add(base);a.base=base;host={body:base,add:c=>actualHost.add(c,base),options:actualHost.options};actualHost.atomS3RExtAssembly=a;
 const board=materials.plastic(0x244b3d,{roughness:.9}),metal=materials.metal(0xb5bcb3,{roughness:.47}),gold=materials.metal(0xc4b487,{roughness:.45}),dark=materials.plastic(0x18221d,{roughness:.83}),white=materials.plastic(0xe7e9e1,{roughness:.68});
 const headerBores=[];for(const [p,labels]of [[DIM.header5,spec.header5Pins],[DIM.header4,spec.header4Pins]])for(let i=0;i<labels.length;i++)headerBores.push({radius:.29,x:p[0],y:p[1]+(labels.length-1)/2*2.54-i*2.54});
 const supportPoints=[[-8.3,8],[8.3,8],[-6,-4.6],[6,-4.6]],mounts=supportPoints.map(([x,y])=>({radius:.3,x,y}));
 a.pcb=mark(plate(host.body,20,20,.8,[0,0,-1.05],board,'C126-Ext ESP32-S3-PICO-1-N8R8 main PCB actual thickness',{radius:1.05,holes:[{radius:1.85,x:0,y:0},...headerBores,...mounts]}),'main-pcb');
 const rearOutline=new THREE.Shape();rearOutline.moveTo(-8.5,-9.7);rearOutline.lineTo(-5.45,-9.7);rearOutline.lineTo(-5.45,-5.4);rearOutline.lineTo(5.45,-5.4);rearOutline.lineTo(5.45,-9.7);rearOutline.lineTo(8.5,-9.7);rearOutline.absarc(8.5,-8.5,1.2,-Math.PI/2,0,false);rearOutline.lineTo(9.7,8.5);rearOutline.absarc(8.5,8.5,1.2,0,Math.PI/2,false);rearOutline.lineTo(-8.5,9.7);rearOutline.absarc(-8.5,8.5,1.2,Math.PI/2,Math.PI,false);rearOutline.lineTo(-9.7,-8.5);rearOutline.absarc(-8.5,-8.5,1.2,Math.PI,Math.PI*1.5,false);rearOutline.closePath();
 for(const [p,n]of [[DIM.header5,5],[DIM.header4,4]]){const cut=new THREE.Path(),x=p[0],y=p[1],w=2.62,h=n*2.54-.12;cut.moveTo(x-w/2,y-h/2);cut.lineTo(x-w/2,y+h/2);cut.lineTo(x+w/2,y+h/2);cut.lineTo(x+w/2,y-h/2);cut.closePath();rearOutline.holes.push(cut);}
 const bore=new THREE.Path();bore.absarc(0,0,3.2,0,Math.PI*2,true);rearOutline.holes.push(bore);
 a.rearCarrier=mark(mesh(host.body,new THREE.ExtrudeGeometry(rearOutline,{depth:.45,bevelEnabled:false,curveSegments:24}),white,[0,0,-5.15],'C126-Ext rear physical receiver retaining carrier'),'rear-retaining-carrier');
 a.imuBoard=mark(plate(host.body,11,13,.65,[0,3,-4.55],board,'C126-Ext BMI270 and BMM150 daughter PCB actual thickness',{radius:.65,holes:[{radius:3.2,x:0,y:-3}]}),'imu-pcb');
 box(host.body,[2.5,3,.8],[0,5.5,-3.5],dark,'C126-Ext BMI270 package visual envelope');box(host.body,[1.6,1.6,.6],[3,5.5,-3.6],dark,'C126-Ext BMM150 package visual envelope');
 for(const [x,y]of supportPoints){annulus(host.body,.55,.28,3.22,[x,y,-4.55],white,'C126-Ext actual PCB retaining standoff');cylinder(host.body,.27,.2,[x,y,-.23],metal,'C126-Ext PCB retaining fastener');}
 a.m2Tube=annulus(host.body,1.63,1.10,3.1,[0,0,-6.2],white,'C126-Ext real M2 blind mounting tube');a.m2Floor=mark(cylinder(host.body,1.10,.2,[0,0,-3],white,'C126-Ext M2 actual deep blind mounting stop'),'mounting-stop');
 a.usb=usbC(host,{id:'usb',position:DIM.usb,face:'bottom',w:8.65,h:3.05,depth:4.85});a.usb.name='C126-Ext complete USB-C receptacle';
 // The own shell has a broad assembly window; this is the real connector/PCB
 // assembly and its insulating surround, never a painted black closure plane.
 const usbSeat=group(host,'C126-Ext USB-C rectangular dielectric package seat',DIM.usb,'bottom');plate(usbSeat,9.7,3.25,4.75,[0,0,-4.75],dark,'C126-Ext USB-C bored rectangular package surround',{radius:.4,holes:[{w:8.75,h:3.15,r:1.575}]});
 for(const x of [-4.5,4.5])box(host.body,[.36,2,1.3],[x,-8.5,1.1],metal,'C126-Ext USB-C actual metal retention');for(let i=0;i<12;i++)box(host.body,[.18,.8,.08],[(i-5.5)*.5,-6.92,.55],gold,'C126-Ext USB-C rear solder termination');
 a.grove=grove(host);a.header5=header(host,'ext-5p',DIM.header5,spec.header5Pins);a.header4=header(host,'ext-4p',DIM.header4,spec.header4Pins);
 for(const side of [-1,1]){box(host.body,[.8,3.3,3.7],[side*5.85,-8.45,-2.75],dark,'C126-Ext Grove socket side insulating seat');box(host.body,[.35,1.5,2.5],[side*5.3,-10.7,-2.7],metal,'C126-Ext Grove retaining clip');}
 box(host.body,[7,7,.8],[2.4,4.5,.18],dark,'C126-Ext ESP32-S3-PICO-1-N8R8 package inferred envelope');box(host.body,[3.5,2.2,1.2],[6.2,8,.37],white,'C126-Ext own PROANT440 antenna inferred placement');
 for(const [x,y]of [[-5,5],[-5.4,7],[-4,7],[-5,-1],[6,-2]]){box(host.body,[1.25,.75,.48],[x,y,-.01],materials.plastic(0xa9a184,{roughness:.83}),'C126-Ext regulator/passive envelope');for(const d of [-.7,.7])box(host.body,[.2,.75,.12],[x+d,y,-.18],metal,'C126-Ext passive solder termination');}
 const resetHousing=group(host,'C126-Ext separate Reset board switch housing',[-9.6,4.5,-2],'left');a.resetSwitch=plate(resetHousing,3,1.4,1.5,[0,0,-1.5],dark,'C126-Ext Reset real bored switch body',{radius:.12,holes:[{radius:.50,x:0,y:0}]});a.resetPlunger=cylinder(host.body,.48,.35,[-9.82,4.5,-2],white,'C126-Ext actual side Reset moving head','x');
 // Passive IR stays a dark physical optic, independent of display commands.
 const ir=group(host,'C126-Ext G47 passive IR assembly');a.ir=ir;plate(ir,1.8,1.6,.20,[-7,9.2,-.15],board,'C126-Ext IR daughter support',{radius:.15});for(const x of [-7.35,-6.65])box(ir,[.15,1.2,.20],[x,10,.2],metal,'C126-Ext IR support/solder lead');cylinder(ir,.25,1.0,[-7,10.85,.2],dark,'C126-Ext IR resin package','y');a.irLens=mesh(ir,new THREE.SphereGeometry(.25,24,16),materials.glossy(0x1b251f,{roughness:.29}),[-7,11.35,.2],'C126-Ext passive IR optical dome');a.irLens.scale.y=.7;
 // Own C126-Ext fixed seated prototype PCB:30 independent real plated bores.
 const proto=group(host,'C126-Ext physical seated prototype and folded FPC');a.prototype=proto;const holes=[];
 for(let c=0;c<5;c++)for(let r=0;r<6;r++)holes.push({radius:.46,x:-1.5+c*2.54,y:-4.2+r*2.54});
 a.protoBoard=plate(proto,21,21,.65,[0,0,4.65],materials.plastic(0xb8a724,{roughness:.74}),'C126-Ext true thick isolated 5x6 prototype PCB',{radius:1.05,holes:holes.map(h=>({...h,radius:.485}))});a.protoHoles=holes;
 a.protoPads=[];for(const h of holes){const pad=annulus(proto,.65,.46,.045,[h.x,h.y,5.30],gold,'C126-Ext isolated annular solder pad');pad.userData.visualFamily='prototype-pad';a.protoPads.push(pad);annulus(proto,.65,.46,.045,[h.x,h.y,4.605],gold,'C126-Ext rear isolated annular solder pad');annulus(proto,.485,.46,.65,[h.x,h.y,4.65],gold,'C126-Ext genuine plated through bore wall');}
 for(const [r,labels]of [[0,['3V3','3V3','2V8','3','9','11','13','17','40','46','GND','GND']],[1,['1V2','RST','4','10','12','14','21','42','48']]])for(let i=0;i<labels.length;i++){const x=r===0?(i-5.5)*1.65:(i-4)*1.9,y=-7.05-r*1.55;plate(proto,1.02,1.02,.04,[x,y,5.30],gold,'C126-Ext powered breakout solder pad '+labels[i],{radius:.02,holes:[{radius:.13}]});}
 // The actual folded 24-trace flex remains an assembled fixed ribbon,not an invented hinge.
 a.fpcConnector=plate(host.body,14.2,3.2,1.05,[0,-6.5,2.15],dark,'C126-Ext real 24P FPC connector with ribbon throat',{radius:.14,holes:[{w:12.2,h:.25,y:0}]});
 for(let i=0;i<24;i++)box(host.body,[.19,2.1,.09],[(i-11.5)*.5,-6.2,2.95],gold,'C126-Ext FPC actual contact '+(i+1));
 a.fpc=box(host.body,[12,9,.16],[0,-1.2,2.9],materials.plastic(0xd6a74c,{roughness:.61}),'C126-Ext thick seated folded flex ribbon');for(let i=0;i<24;i++)box(host.body,[.10,8.6,.012],[(i-11.5)*.49,-1.2,2.987],gold,'C126-Ext flex conductor visual '+(i+1));
 box(host.body,[12,1.2,.7],[0,3.4,3.8],materials.plastic(0xd6a74c,{roughness:.61}),'C126-Ext folded flex return into prototype connector');box(host.body,[13,1.8,.6],[0,3.3,4.28],dark,'C126-Ext prototype rear FPC receiver');
 a.reset=actualHost.add(new NativeReset(parts['lower-shell']));a.reset.follow(a.resetPlunger);
 a.ir.position.z+=.30;
 return a;
}
