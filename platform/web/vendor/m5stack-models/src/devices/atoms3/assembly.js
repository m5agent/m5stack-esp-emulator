// MIT. Original C123 own native enclosure plus photograph-registered physical internals.
// Hidden package, support and travel dimensions are appearance inferences, not manufacturing CAD.
import {Port,Display,Button} from '../../core/index.js';
import {usbC} from '../../modeling/connectors.js';
import {THREE,materials,FACE,portQuaternion,mesh,box,plate,cylinder,annulus,ownNative} from './geometry.js';
import {NativeReset} from './NativeReset.js';
import native from './native-data.js';
import {DIM,spec} from './dimensions.js';
const mark=(o,family)=>{o.userData.visualFamily=family;return o;};
function group(host,name,p=[0,0,0],face){const g=new THREE.Group();g.name=name;g.position.fromArray(p);if(face)g.quaternion.copy(FACE[face]);host.body.add(g);return g;}
function header(host,id,p,labels){
 const n=labels.length,g=group(host,'C123 '+id+' physical female receiver',p,'back'),dark=materials.plastic(0x141b17,{roughness:.81}),gold=materials.metal(0xc4b586,{roughness:.43}),ys=labels.map((_,i)=>(n-1)/2*2.54-i*2.54),holes=ys.map(y=>({w:1.02,h:1.02,r:.055,y}));
 mark(plate(g,2.54,n*2.54-.2,2.2,[0,0,-2.2],dark,'C123 '+id+' bored closed molded housing',{radius:.04,holes}),'female-header-housing');
 for(let i=0;i<n;i++){const y=ys[i];mark(box(g,[1.02,1.02,.12],[0,y,-2.14],dark,'C123 '+id+' socket '+(i+1)+' recessed floor'),'header-socket-floor');for(const sign of [-1,1]){const c=mark(box(g,[.12,.66,1.28],[sign*.34,y,-1.12],gold,'C123 '+id+' socket '+(i+1)+' actual spring contact'),'header-spring-contact');c.userData.pin=i+1;}mark(cylinder(host.body,.15,3.4,[p[0],p[1]+y,-2.4],gold,'C123 '+id+' pin '+(i+1)+' solder tail'),'header-tail');}
 host.add(new Port({id,label:'C123 '+n+'-pin female expansion',connector:'m5.atom.ext-'+n+'p',position:p,quaternion:portQuaternion('back'),hitSize:[2.82,1,n*2.54+.1],pins:labels.map((name,i)=>({n:i+1,name,signal:name})),pinGrid:{cols:1,rows:n,pitch:2.54,center:[0,0],order:(_c,r)=>n-r},meta:{face:'back',role:'visual-connector',gender:'female',scope:'Documented labels and mechanical frame only;no electrical or protocol simulation'}}));return g;
}
function grove(host){
 const g=group(host,'C123 HY2.0-4P complete receiver',DIM.grove,'bottom'),white=materials.plastic(0xe6e9df,{roughness:.66}),metal=materials.metal(0xc0b487,{roughness:.42});
 mark(plate(g,10.8,3.5,6.25,[0,0,-6.25],white,'C123 Grove keyed molded walls',{radius:.22,holes:[{w:8.7,h:2.65,r:.15}]}),'grove-receiver');mark(box(g,[8.68,2.64,.5],[0,0,-6],white,'C123 Grove physical dielectric rear wall'),'grove-rear-wall');
 for(const x of [-4.4,4.4])box(g,[.65,.58,1.3],[x,1.1,-.5],white,'C123 Grove actual latch rail');
 const contacts=[];for(let i=0;i<4;i++){const x=(i-1.5)*2,c=mark(box(g,[.4,.4,4.7],[x,-.2,-3.4],metal,'C123 Grove contact '+(i+1)),'grove-contact');c.userData.pin=i+1;contacts.push(c);mark(box(g,[.4,.4,1.1],[x,-.2,-6.55],metal,'C123 Grove rear tail '+(i+1)),'grove-tail');cylinder(host.body,.17,2.4,[x,-5.47,-2.15],metal,'C123 Grove PCB solder return');}
 for(const x of [-5,5])box(host.body,[.45,1.3,1.2],[x,-7,-2.9],metal,'C123 Grove retention foot');
 host.add(new Port({id:'grove',label:'C123 HY2.0-4P · GND/5V/G2/G1',connector:'grove',position:DIM.grove,quaternion:portQuaternion('bottom'),hitSize:[10.8,1,3.5],pins:spec.grovePins.map((name,i)=>({n:i+1,name,signal:name})),meta:{face:'bottom',role:'visual-connector',scope:'Four-wire mechanical connection only;no I2C/UART/power simulation'}}));return {group:g,contacts};
}
export function buildAssembly(host){
 const parts=ownNative(host,native),a={parts};host.atomS3Assembly=a;
 const board=materials.plastic(0x244b3d,{roughness:.9}),metal=materials.metal(0xb5bcb3,{roughness:.47}),gold=materials.metal(0xc4b487,{roughness:.45}),dark=materials.plastic(0x18221d,{roughness:.83}),white=materials.plastic(0xe7e9e1,{roughness:.68});
 const headerBores=[];for(const [p,labels]of [[DIM.header5,spec.header5Pins],[DIM.header4,spec.header4Pins]])for(let i=0;i<labels.length;i++)headerBores.push({radius:.29,x:p[0],y:p[1]+(labels.length-1)/2*2.54-i*2.54});
 const supportPoints=[[-8.3,8],[8.3,8],[-6,-4.6],[6,-4.6]],mounts=supportPoints.map(([x,y])=>({radius:.3,x,y}));
 a.pcb=mark(plate(host.body,20,20,.8,[0,0,-1.05],board,'C123 ESP32-S3FN8 main PCB actual thickness',{radius:1.05,holes:[{radius:1.85,x:0,y:0},...headerBores,...mounts]}),'main-pcb');
 const rearOutline=new THREE.Shape();rearOutline.moveTo(-8.5,-9.7);rearOutline.lineTo(-5.45,-9.7);rearOutline.lineTo(-5.45,-5.4);rearOutline.lineTo(5.45,-5.4);rearOutline.lineTo(5.45,-9.7);rearOutline.lineTo(8.5,-9.7);rearOutline.absarc(8.5,-8.5,1.2,-Math.PI/2,0,false);rearOutline.lineTo(9.7,8.5);rearOutline.absarc(8.5,8.5,1.2,0,Math.PI/2,false);rearOutline.lineTo(-8.5,9.7);rearOutline.absarc(-8.5,8.5,1.2,Math.PI/2,Math.PI,false);rearOutline.lineTo(-9.7,-8.5);rearOutline.absarc(-8.5,-8.5,1.2,Math.PI,Math.PI*1.5,false);rearOutline.closePath();
 for(const [p,n]of [[DIM.header5,5],[DIM.header4,4]]){const cut=new THREE.Path(),x=p[0],y=p[1],w=2.62,h=n*2.54-.12;cut.moveTo(x-w/2,y-h/2);cut.lineTo(x-w/2,y+h/2);cut.lineTo(x+w/2,y+h/2);cut.lineTo(x+w/2,y-h/2);cut.closePath();rearOutline.holes.push(cut);}
 const bore=new THREE.Path();bore.absarc(0,0,3.2,0,Math.PI*2,true);rearOutline.holes.push(bore);
 a.rearCarrier=mark(mesh(host.body,new THREE.ExtrudeGeometry(rearOutline,{depth:.45,bevelEnabled:false,curveSegments:24}),white,[0,0,-5.15],'C123 rear physical receiver retaining carrier'),'rear-retaining-carrier');
 a.imuBoard=mark(plate(host.body,11,13,.65,[0,3,-4.55],board,'C123 MPU6886 daughter PCB actual thickness',{radius:.65,holes:[{radius:3.2,x:0,y:-3}]}),'imu-pcb');
 box(host.body,[3,3,.8],[0,5.5,-3.5],dark,'C123 MPU6886 package visual envelope');
 for(const [x,y]of supportPoints){annulus(host.body,.55,.28,3.22,[x,y,-4.55],white,'C123 actual PCB retaining standoff');cylinder(host.body,.27,.2,[x,y,-.23],metal,'C123 PCB retaining fastener');}
 a.m2Tube=annulus(host.body,1.63,1.10,3.1,[0,0,-6.2],white,'C123 real M2 blind mounting tube');a.m2Floor=mark(cylinder(host.body,1.10,.2,[0,0,-3],white,'C123 M2 actual deep blind mounting stop'),'mounting-stop');
 a.usb=usbC(host,{id:'usb',position:DIM.usb,face:'bottom',w:8.65,h:3.05,depth:4.85});a.usb.name='C123 complete USB-C receptacle';
 // The own shell has a broad assembly window; this is the real connector/PCB
 // assembly and its insulating surround, never a painted black closure plane.
 const usbSeat=group(host,'C123 USB-C rectangular dielectric package seat',DIM.usb,'bottom');plate(usbSeat,9.7,3.7,4.75,[0,0,-4.75],dark,'C123 USB-C bored rectangular package surround',{radius:.4,holes:[{w:8.75,h:3.15,r:1.575}]});
 for(const x of [-4.5,4.5])box(host.body,[.36,2,1.3],[x,-8.5,1.1],metal,'C123 USB-C actual metal retention');for(let i=0;i<12;i++)box(host.body,[.18,.8,.08],[(i-5.5)*.5,-6.92,.55],gold,'C123 USB-C rear solder termination');
 a.grove=grove(host);a.header5=header(host,'ext-5p',DIM.header5,spec.header5Pins);a.header4=header(host,'ext-4p',DIM.header4,spec.header4Pins);
 for(const side of [-1,1]){box(host.body,[.8,3.3,3.7],[side*5.85,-8.45,-2.75],dark,'C123 Grove socket side insulating seat');box(host.body,[.35,1.5,2.5],[side*5.3,-10.7,-2.7],metal,'C123 Grove retaining clip');}
 box(host.body,[7,7,.8],[2.4,4.5,.18],dark,'C123 ESP32-S3FN8 package inferred envelope');box(host.body,[3.5,2.2,1.2],[6.2,8,.37],white,'C123 own PROANT440 antenna inferred placement');
 for(const [x,y]of [[-5,5],[-5.4,7],[-4,7],[-5,-1],[6,-2]]){box(host.body,[1.25,.75,.48],[x,y,-.01],materials.plastic(0xa9a184,{roughness:.83}),'C123 regulator/passive envelope');for(const d of [-.7,.7])box(host.body,[.2,.75,.12],[x+d,y,-.18],metal,'C123 passive solder termination');}
 a.mainSwitch=plate(host.body,3.5,3.5,1.3,[0,-2,-.25],dark,'C123 G41 LCD PCB switch bored housing',{radius:.15,holes:[{radius:.8,x:0,y:0}]});for(const x of [-1.7,1.7])for(const y of [-3.4,-.6])box(host.body,[.55,.55,.18],[x,y,-.16],metal,'C123 G41 switch solder terminal');
 a.mainPlunger=cylinder(host.body,.72,1.7,[0,-2,1.7],white,'C123 actual LCD-key moving plunger');
 const resetHousing=group(host,'C123 separate Reset board switch housing',[-9.6,4.5,-2],'left');a.resetSwitch=plate(resetHousing,3,1.4,1.5,[0,0,-1.5],dark,'C123 Reset real bored switch body',{radius:.12,holes:[{radius:.50,x:0,y:0}]});a.resetPlunger=cylinder(host.body,.48,.35,[-9.82,4.5,-2],white,'C123 actual side Reset moving head','x');
 // Passive IR stays a dark physical optic, independent of display commands.
 const ir=group(host,'C123 G4 passive IR assembly');a.ir=ir;plate(ir,1.8,1.6,.20,[-7,9.2,-.15],board,'C123 IR daughter support',{radius:.15});for(const x of [-7.35,-6.65])box(ir,[.15,1.2,.20],[x,10,.2],metal,'C123 IR support/solder lead');cylinder(ir,.25,1.0,[-7,10.85,.2],dark,'C123 IR resin package','y');a.irLens=mesh(ir,new THREE.SphereGeometry(.25,24,16),materials.glossy(0x1b251f,{roughness:.29}),[-7,11.35,.2],'C123 passive IR optical dome');a.irLens.scale.y=.7;
 // The LCD, cover glass and complete panel module are one rigid press assembly.
 const screen=new THREE.Group();screen.name='C123 complete pressable LCD stack';
 a.lcdModule=plate(screen,17.5,17.5,1.82,[0,0,3.3],dark,'C123 LCD actual thick module body',{radius:.65});
 a.lcdBackplate=plate(screen,17.3,17.3,.28,[0,0,3.02],metal,'C123 LCD rear metal supporting plate',{radius:.6});
 a.lcdRiser=plate(screen,16.10,16.10,.65,[0,0,5.12],dark,'C123 inner stepped LCD optical support',{radius:.7});
 a.lcdBezel=plate(screen,16.10,16.10,.35,[0,0,5.77],dark,'C123 thick LCD glass carrier with real active opening',{radius:.7,holes:[{w:15.3,h:15.3,r:.05}]});
 a.lcdGlass=plate(screen,16.2,16.2,.18,[0,0,6.12],materials.glossy(0x111719,{roughness:.17,clearcoat:.22}),'C123 solid cover-glass optical substrate',{radius:.3});
 // Display owns its shader/texture. Register it before Button so disposal removes
 // its object before the cap is released; the same resource is never owned twice.
 const lcd=host.add(new Display({id:'lcd',label:'C123 0.85-inch 128×128 IPS LCD',width:128,height:128,size:[spec.lcd.activeMm,spec.lcd.activeMm],position:DIM.lcd,pixelEffect:true,touch:false,glass:false,meta:{role:'external-framebuffer',driver:'GC9107 documented;not emulated',scope:'External pixels/backlight only;not touch or automatic boot rendering'}}));
 screen.add(lcd.object3d);a.lcd=lcd;
 a.lcdFlex=plate(screen,17.5,1.1,.12,[0,-11.8,4.4],materials.plastic(0xc4a447,{roughness:.75}),'C123 folded LCD physical flex insulating carrier',{radius:.05});a.lcdFlex.quaternion.copy(FACE.bottom);plate(screen,17.5,2.3,.12,[0,-10.55,4.2],materials.plastic(0xc4a447,{roughness:.75}),'C123 real bent flex return to LCD module',{radius:.05});
 const button=host.add(new Button({id:'button',label:'C123 programmable LCD key · G41',mesh:screen,travel:spec.travelMm.button,longPressMs:0,meta:{gpio:'G41',role:'visual-control',actuation:'momentary',surfaceCenter:DIM.lcd,surfaceFace:'front',scope:'Actual LCD stack visual press and input intent only;no firmware effect',travelSource:'C123 own photos inferred appearance;not rated travel'}}));a.button=button;
 // Only a physically thin switch head follows the LCD; fixed PCB/supports stay.
 button.cap.add(a.mainPlunger);a.reset=host.add(new NativeReset(parts['lower-shell']));a.reset.follow(a.resetPlunger);
 return a;
}
