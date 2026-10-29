/** MIT. Complete K001-V27 visual assembly. Own native frame/keys plus explicit reconstruction. */
import {Button,Port,Display} from '../../core/index.js';
import {usbC,microSD} from '../../modeling/connectors.js';
import {nativeMesh} from './native.js';
import {spec} from './dimensions.js';
import {THREE,materials,box,cylinder,slab,ring,tube,frame,header,grove,portQuaternion,FACE} from './geometry.js';
const physical=(o,role='physical-reconstruction')=>{o.userData.role=role;return o;};
function port(host,id,connector,position,face,pins,cols,rows,pitch=2.54){return host.add(new Port({id,label:'K001-V27 '+id,connector,position,quaternion:portQuaternion(face),hitSize:[cols*pitch+.5,1,rows*pitch+.5],pins:pins.map((name,i)=>({n:i+1,name})),pinGrid:{cols,rows,pitch,center:[0,0],order:(c,r)=>r*cols+c+1},meta:{face,role:'visual-connector',scope:'Mechanical appearance only;firmware,power and bus behavior external'}}));}
function mbusSocket(parent,position,black,metal){
 const f=frame(parent,position,'back','K001-V27 complete host M-Bus socket assembly'),holes=[],contacts=[],stops=[];
 for(let r=0;r<15;r++)for(let c=0;c<2;c++)holes.push({w:1.18,h:1.18,r:.025,cx:(c-.5)*2.54,cy:(r-7)*2.54});
 const housing=slab(f,5.58,38.6,1.8,.25,[0,0,-1.8],black,holes,0);housing.name='M-Bus closed molded 30-well housing';
 for(const h of holes){stops.push(box(f,[1.18,1.18,.1],[h.cx,h.cy,-1.9],black,'M-Bus socket deep insulating floor'));for(const sign of[-1,1])contacts.push(box(f,[.15,.72,.9],[h.cx+sign*.4,h.cy,-.82],metal,'M-Bus recessed spring contact'));}
 return{frame:f,housing,holes,contacts,stops};
}
function moldedBrand(base,material){
 const f=frame(base,[0,0,-8.5],'back','K001-V27 original reconstructed molded brand relief');
 const stroke=(a,b,width=.22)=>{const dx=b[0]-a[0],dy=b[1]-a[1],o=box(f,[Math.hypot(dx,dy),width,.13],[(a[0]+b[0])/2,(a[1]+b[1])/2,.065],material,'Physical raised molded brand stroke');o.rotation.z=Math.atan2(dy,dx);};
 const lines=[[[-6,5],[-1.5,8],[6,4.5],[1.5,1],[-6,5]],[[-6,5],[-6,-.4],[1.5,-4],[6,-.6],[6,4.5]],[[-4.8,4.9],[-1.6,6.9],[1.5,5.4],[-1.7,3.7]],[[-.5,3.6],[1.8,4.8],[3.6,4],[1.3,2.8]]];for(const line of lines)for(let i=1;i<line.length;i++)stroke(line[i-1],line[i],.3);
 const glyph={M:[[0,0,0,3],[0,3,1,1.4],[1,1.4,2,3],[2,3,2,0]],5:[[2,3,0,3],[0,3,0,1.5],[0,1.5,2,1.5],[2,1.5,2,0],[2,0,0,0]],S:[[2,3,0,3],[0,3,0,1.5],[0,1.5,2,1.5],[2,1.5,2,0],[2,0,0,0]],T:[[0,3,2,3],[1,3,1,0]],A:[[0,0,1,3],[1,3,2,0],[.4,1.2,1.6,1.2]],C:[[2,3,0,3],[0,3,0,0],[0,0,2,0]],K:[[0,0,0,3],[0,1.5,2,3],[0,1.5,2,0]],0:[[0,0,0,3],[0,3,2,3],[2,3,2,0],[2,0,0,0]],1:[[1,0,1,3],[.3,2.4,1,3]]};
 for(let i=0;i<7;i++)for(const[a,b,c,d]of glyph['M5STACK'[i]])stroke([i*3-10+a,-10+b],[i*3-10+c,-10+d],.2);
 for(const[ch,y]of[['0',3.2],['1',13.4]])for(const[a,b,c,d]of glyph[ch])stroke([9.9+a*.55,y+b*.55],[9.9+c*.55,y+d*.55],.14);
 return f;
}
function originalBase(host,a){
 const base=new THREE.Group();base.name='K001-V27 original revised battery base reconstruction';host.body.add(base);a.base=base;
 const black=materials.plastic(0x222627,{roughness:.8}),rubber=materials.plastic(0x101413,{roughness:.96}),board=materials.plastic(0x204333,{roughness:.92}),metal=materials.metal(0xb6b6ad,{roughness:.48});
 const mount=[[-22,-22],[22,-22]],feet=[[-17.2,16.8],[17.2,16.8],[-17.2,-15.5],[17.2,-15.5]],holes=[{w:spec.switch.slot[0],h:spec.switch.slot[1],r:.18,cx:spec.switch.position[0],cy:spec.switch.position[1]},...mount.map(([x,y])=>({w:5.5,h:5.5,r:2.75,cx:x,cy:y})),...feet.map(([x,y])=>({w:8,h:8,r:4,cx:x,cy:y}))];
 a.rearPlate=physical(slab(base,53.92,53.92,1.0,4.1,[0,0,-8.5],black,holes,.04));a.rearPlate.name='Original rear plate with true switch,feet and fastener apertures';
 a.rearBands=[ring(base,53.92,53.92,1.3,4.1,50.82,50.82,[0,0,-7.5],black,'Rear base lower continuous rim'),ring(base,53.92,53.92,.8,4.1,50.82,50.82,[0,0,-4.1],black,'Rear base upper continuous rim')];
 // Four true lateral pin-access windows, with thick closed jambs and rounded corner material.
 for(const sx of[-1,1])for(const sy of[-1,1]){
  box(base,[4.125,1.55,2.1],[sx*20.7975,sy*26.185,-5.15],black,'Base side-access window jamb');box(base,[1.55,4.125,2.1],[sx*26.185,sy*20.7975,-5.15],black,'Base perpendicular window jamb');
  const g=new THREE.Shape();g.absarc(0,0,4.1,0,Math.PI/2,false);g.lineTo(0,2.55);g.absarc(0,0,2.55,Math.PI/2,0,true);g.closePath();
  const corner=new THREE.Mesh(new THREE.ExtrudeGeometry(g,{depth:2.1,bevelEnabled:false,curveSegments:24}),black);corner.rotation.z=(sx===1?sy===1?0:-Math.PI/2:sy===1?Math.PI/2:Math.PI);corner.position.set(sx*22.86,sy*22.86,-6.2);corner.name='Rear base rounded corner wall';base.add(corner);
 }
 a.feet=[];for(const[x,y]of feet){a.feet.push(cylinder(base,3.94,.87,[x,y,-8.0],rubber,'Supported recessed rubber foot'));cylinder(base,4.04,.2,[x,y,-7.45],black,'Foot pocket deep support');}
 a.mounts=[];for(const[x,y]of mount){const bore=tube(base,2.75,1.35,3.8,[x,y,-7.5],black,'Stepped rear mounting bore');a.mounts.push(bore);const screw=cylinder(base,1.22,.6,[x,y,-5.9],metal,'Deep retained screw head');box(base,[.85,.14,.04],[x,y,-6.22],rubber,'Screw driver slot bottom');}
 a.baseBoard=physical(slab(base,48.4,48.4,.8,2,[0,0,-5.4],board,[...mount.map(([x,y])=>({w:3.0,h:3.0,r:1.5,cx:x,cy:y}))],.03));a.baseBoard.name='Supported battery-base PCB';for(let r=0;r<15;r++)for(let c=0;c<2;c++)box(base,[.45,.45,1.25],[21+(c-.5)*2.54,(r-7)*2.54,-3.98],metal,'Base M-Bus male mating pin');
 // Supported cell enclosed by the base; its shape is a visual estimate, not a hidden BOM assertion.
 a.battery=box(base,[24,19,1.7],[4,-6,-6.7],materials.metal(0xb8b6a9,{roughness:.68}),'110 mAh enclosed battery appearance envelope');
 for(const[x,y]of[[-20,20],[20,20],[-19,-18],[19,-18]])tube(base,1.6,.7,3.2,[x,y,-7.4],black,'Battery base board support boss');
 const sw=spec.switch,carrier=frame(base,[sw.position[0],sw.position[1],-8.5],'back','Actual rear slide mechanism and supporting carrier');
 a.switchCarrier=slab(carrier,6.2,9,1.3,.4,[0,0,-2.6],black,[{w:3.5,h:7.1,r:.12}],.02);a.switchCarrier.name='Rear switch bored fixed carrier';a.switchStop=box(carrier,[6.2,9,.3],[0,0,-2.75],rubber,'Rear switch deep fixed backstop');
 for(const x of[-2.6,2.6])for(const y of[-2.6,2.6])box(carrier,[.5,1.1,.3],[x,y,-2.3],metal,'Switch retained solder/contact tail');
 const cap=new THREE.Group();cap.name='Rear two-detent physical switch cap';box(cap,[2.45,2.4,1.6],[0,0,-.7],rubber.clone(),'Rear switch moving actuator');for(const y of[-.65,0,.65])box(cap,[2.35,.14,.18],[0,y,.17],black.clone(),'Rear switch grip ridge');
 const toggle=host.add(new Button({id:'power-switch',label:'Rear power slide · mechanical detent',mesh:cap,travel:sw.travelMm,axis:[0,1,0],position:[sw.position[0],sw.position[1]-sw.travelMm/2,-8.5],latching:true,longPressMs:0,meta:{role:'visual-two-detent-slide',actuation:'stable-slide',positionUnit:'detent',range:[0,1],motion:'2.8 mm along +Y;no electrical power behavior'}}));toggle.object3d.quaternion.copy(FACE.back);toggle.setPosition(1,{immediate:true});a.powerSwitch=toggle;a.moldedBrand=moldedBrand(base,black);
 // These are the photographed base's edge-access rows; each has a real recessed contact and socket well.
 a.edgeHeaders=[];for(const[face,pos,count]of[['left',[-26.0,0,-5.15],15],['right',[26.0,0,-5.15],15],['top',[0,26.0,-5.15],8],['bottom',[0,-26.0,-5.15],8]]){
  const f=frame(base,pos,face,'Base '+face+' physical edge header');const pitch=2.54,w=count*pitch+.2,well=.98,holes=Array.from({length:count},(_,i)=>({w:well,h:well,r:.03,cx:(i-(count-1)/2)*pitch,cy:0}));const housing=slab(f,w,1.6,1.6,.12,[0,0,-1.6],black,holes,0);housing.name='Base '+face+' true single-row socket housing';const contacts=[],stops=[];for(let i=0;i<count;i++){const x=(i-(count-1)/2)*pitch;stops.push(box(f,[well,well,.15],[x,0,-1.8],rubber,'Base edge socket deep floor'));contacts.push(box(f,[.24,.7,.75],[x,0,-1.1],metal,'Base edge recessed contact'));}a.edgeHeaders.push({face,frame:f,housing,contacts,stops,count});
 }
 return base;
}
export function buildAssembly(host){
 const a={native:{},buttons:[],films:{},artworkPanels:[]},black=materials.plastic(0x202526,{roughness:.76}),silver=materials.metal(0xced0cf,{roughness:.4}),red=materials.plastic(0xbc3c48,{roughness:.67}),pcb=materials.plastic(0x202b27,{roughness:.94}),dark=materials.plastic(0x111918,{roughness:.93});host.basicV27Assembly=a;
 a.native.middle=nativeMesh('middle',black);host.body.add(a.native.middle);
 // Native button coordinates remain original; local rigid offsets provide meaningful component centres.
 for(const b of spec.buttons){const cap=nativeMesh('front-button',silver.clone());cap.position.add(new THREE.Vector3(12,21,-8.5));const button=host.add(new Button({id:b.id,label:b.label,mesh:cap,position:b.center,travel:b.travelMm,longPressMs:0,meta:{pin:b.pin,actuation:'rigid-native-cap',sourcePart:'K001-V27 supplied Button STL',sourceInstance:b.id,travelBasis:'Photo-derived visual estimate;no datasheet actuation distance',fixedFrame:true}}));a.native[b.id]=cap;a.buttons.push(button);}
 const powerCap=nativeMesh('side-button',red);powerCap.position.sub(new THREE.Vector3(...spec.power.position));a.power=host.add(new Button({id:'power',label:'Power / Reset · input intent',mesh:powerCap,position:spec.power.position,axis:[1,0,0],travel:spec.power.travelMm,longPressMs:0,meta:{actuation:'rigid-native-cap',scope:'Input intention only;no reset/power/firmware behavior'}}));a.native.power=powerCap;a.buttons.push(a.power);
 const buttonHoles=spec.buttons.map(b=>({w:9.34,h:5.94,r:1,cx:b.center[0],cy:b.center[1]}));a.cover=physical(slab(host.body,51.15,51.15,.55,3.7,[0,0,7.9],materials.glossy(0x080d0e,{roughness:.18}),[{w:40.64,h:30.48,r:.12,cx:0,cy:2.8},...buttonHoles],.03));a.cover.name='Original K001-V27 black cover-glass perimeter with three true key openings';
 a.lcdGlass=physical(slab(host.body,40.64,30.48,.55,.12,[0,2.8,7.9],materials.glossy(0x12201e,{roughness:.11}),[],.025));a.lcdGlass.name='Actual thick supported LCD front optical substrate';a.lcdBack=physical(slab(host.body,45,35.4,1.9,.7,[0,2.8,5.95],materials.metal(0x747f7e,{roughness:.65}),[],.05));a.lcdBack.name='LCD thick backlight and frame support';
 a.display=host.add(new Display({id:'lcd',label:'2.0-inch ILI9342C · external framebuffer',width:320,height:240,size:spec.display.size,position:spec.display.position,touch:false,glass:{intensity:.14,roughness:.12},meta:{role:'external-framebuffer',touch:false,registration:'Exact product photo;active area diagonal-derived',scope:'Pixels/backlight supplied externally;no firmware test-screen or touch'}}));
 a.mainBoard=physical(slab(host.body,48.2,48.2,.85,1.7,[0,0,-2.35],pcb,[{w:3.1,h:3.1,r:1.55,cx:-22,cy:-22},{w:3.1,h:3.1,r:1.55,cx:22,cy:-22}],.035));a.mainBoard.name='Original supported K001-V27 main PCB appearance';
 a.displayCarrier=physical(slab(host.body,43.8,36.4,.9,.6,[0,2.8,4.9],pcb,[],.03));a.displayCarrier.name='Independent LCD carrier supporting glass assembly';a.keySupports=[];for(const b of spec.buttons){const bridge=box(host.body,[8.6,7.1,.8],[b.center[0],-21,4.4],pcb,'Front key supported carrier board');const sw=box(host.body,[6.1,3.3,.7],[b.center[0],-21,5.15],dark,'Fixed front tactile package');box(host.body,[3.8,2.2,.35],[b.center[0],-21,5.65],silver,'Fixed tactile actuator clearance reference');a.keySupports.push({bridge,switch:sw});for(const dx of[-3.3,3.3])box(host.body,[.8,1.2,.15],[b.center[0]+dx,-21,4.9],silver,'Front switch retained contact leg');}
 for(const[x,y]of[[-20,18],[20,18],[-18,-16],[18,-16]]){tube(host.body,1.8,.9,6,[x,y,-1.4],black,'LCD/mainboard spaced support post');cylinder(host.body,.8,.45,[x,y,4.7],silver,'LCD carrier retained fastener');}
 a.powerSupport=box(host.body,[.8,8,3.7],[-23.2,13,1.1],dark,'Fixed supported side power switch body');for(const y of[10.4,15.6])box(host.body,[1.4,.6,.6],[-23.4,y,1.1],silver,'Side switch contact solder tail');
 a.usb=usbC(host,{id:null,position:spec.usb.position,face:'left',w:8.45,h:2.95,depth:5.5});a.usb.name='Own K001-V27 full USB-C shell,tongue,24 pads and deep stop';a.usbPort=port(host,'usb','usb-c',spec.usb.position,'left',[],1,1);box(host.body,[2,10,.8],[-21.2,0,-1.05],pcb,'USB-C board support');for(const y of[-3.2,3.2])box(host.body,[1.6,.7,.35],[-23,y,-.8],silver,'USB-C retention solder lug');
 a.grove=grove(host,{position:spec.grove.position,face:'left',id:'grove',w:10,h:4.75,depth:6.0,color:0xc72f37});a.grove.name='Own red Port A full HY2.0-4P and deep contact stop';for(const child of [...a.grove.children])if(child.geometry?.type==='PlaneGeometry'){child.removeFromParent();child.geometry.dispose();child.material.dispose();}a.groveStop=box(a.grove,[8.4,3.2,.18],[0,0,-5.35],dark,'Closed Grove dielectric deep stop');const gp=host.port('grove');gp.pins=spec.grove.pins.map((name,i)=>({n:i+1,name}));gp.pinGrid={cols:4,rows:1,pitch:2,center:[0,0],order:c=>4-c};gp.meta={...gp.meta,role:'visual-connector',scope:'Mechanical Grove cable;I2C/address/power and GPIO external'};box(host.body,[2.4,11.2,.9],[-20.5,-14,-2.6],pcb,'Grove retained PCB land');for(const y of[-17,-15,-13,-11])box(host.body,[1.8,.45,.4],[-20.3,y,-2.0],silver,'Grove visible retained solder tail');
 a.sd=microSD(host,{id:null,position:spec.microSD.position,face:'bottom',w:12.3,h:1.7,depth:10.5});a.sd.name='Full empty microSD receptacle with deep guide,8 contacts and stop';box(host.body,[16.7,8.6,.2],[-6.5,-20.1,1.7],silver,'microSD wider internal retained shield');a.sdPort=port(host,'micro-sd','micro-sd',spec.microSD.position,'bottom',[],1,1);box(host.body,[18.5,2.1,.65],[-6.5,-16,-.5],pcb,'microSD retained board support');
 a.mbus=mbusSocket(host.body,spec.mbus.position,dark,silver);a.mbus.frame.name='Actual host M-Bus 2x15 female sockets with thirty real wells';a.mbusPort=port(host,'mbus','m5.bus.30',spec.mbus.position,'back',spec.mbus.pins,2,15);a.mbusPort.pinGrid.order=(c,r)=>r*2+(1-c)+1;a.mbusPort.meta.access=host.options.base==='removed'?'exposed':'concealed by installed battery base';
 a.esp=box(host.body,[14,15.4,1.2],[-1,1,-3.0],materials.metal(0x9ba19c,{roughness:.66}),'ESP32 shield appearance envelope');a.espFilm=physical(slab(host.body,13.4,17.2,.055,.08,[-1.4,1.1,-3.66],materials.plastic(0xe0e0db,{roughness:.88}),[],.005),'physical-label-substrate');a.espFilm.name='Real PCB pinmap label substrate';
 a.speaker=frame(host.body,[25,5,2],'right','Passive speaker and sealed sound channel behind actual native three-row grille');box(a.speaker,[28,6.7,2.4],[0,0,-1.5],dark,'Closed speaker sound-channel package');box(a.speaker,[25,5.8,.2],[0,0,-.15],materials.plastic(0x252c29,{roughness:.95}),'Actual passive speaker diaphragm/channel face');
 for(const[x,y]of[[-7,17],[10,12],[-7,-10],[10,-9]]){box(host.body,[4.5,3.7,.8],[x,y,-2.9],dark,'Rear supported passive IC package');for(const dx of[-2.4,2.4])for(const dy of[-1.2,0,1.2])box(host.body,[.4,.4,.22],[x+dx,y+dy,-2.7],silver,'Rear IC retained contact lead');}
 if(host.options.base!=='removed')originalBase(host,a);
 return a;
}
