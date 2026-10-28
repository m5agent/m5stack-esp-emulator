import{Port}from'../../core/index.js';
import{THREE,mesh,FACE,portQuaternion,materials,solid,hole,ribbon}from'./geometry.js';
import{WhiteOledDisplay}from'./WhiteOledDisplay.js';
import{spec}from'./dimensions.js';
import{addStickers}from'./stickers.js';

const box=(parent,size,p,mat,name)=>mesh(parent,new THREE.BoxGeometry(...size),mat,p,name);
function pcb(host){
 const shape=new THREE.Shape(),outline=[[-12.9,6],[12.9,6],[12.9,3.5],[11.95,3.5],[11.95,-3.5],[12.9,-3.5],[12.9,-6],[6,-6],[5.75,-5.65],[5.05,-5.65],[4.8,-6],[-4.8,-6],[-5.05,-5.65],[-5.75,-5.65],[-6,-6],[-12.9,-6],[-12.9,-3.5],[-11.95,-3.5],[-11.95,3.5],[-12.9,3.5]];
 outline.forEach(([x,y],i)=>i?shape.lineTo(x,y):shape.moveTo(x,y));shape.closePath();for(const[x,y]of spec.pcb.unmarkedBoresMm)hole(shape,x,y,.4);
 const pcb=solid(host.body,shape,1,[0,0,-3.2],materials.plastic(0x151b17,{roughness:.83}),'Mini OLED own black PCB with four unmarked open bores');
 pcb.userData={role:'physical-pcb',sourceRoute:'own-dimensioned-parametric-no-CAD',scope:'Own U166 outline and population; fine outline and unmarked bores inferred. No mounting function asserted.'};
 const metal=materials.metal(0xb1b6ae,{roughness:.48}),black=materials.plastic(0x242623,{roughness:.82}),ceramic=materials.plastic(0xa7a862,{roughness:.8}),lands=[],passives=[],terminations=[];
 const ht=box(host.body,[2.4,2.2,.72],[-.55,-1.95,-1.84],black,'HT7533 actual three-terminal regulator body'),htPins=[];
 for(const[x,y,w,h]of[[-1.65,-.55,.45,.75],[.55,-.55,.45,.75],[-.55,-3.5,.45,.9]]){lands.push(box(host.body,[w+.12,h+.1,.035],[x,y,-2.1825],metal,'HT7533 solderland'));htPins.push(box(host.body,[w,h,.13],[x,y,-2.115],metal,'HT7533 actual functional terminal'));}
 const positions=[[-4.15,4.45],[-3.25,4.45],[-2.3,4.45],[-1.35,4.45],[-.4,4.45],[.55,4.45],[1.5,4.45],[2.45,4.45],[3.4,4.45],[4.35,4.45],[0,.25],[-3.2,-4.65],[-2.3,-4.65],[1.55,-2.35],[2.5,-2.35]];
 for(let i=0;i<positions.length;i++){const[x,y]=positions[i],isR=i>=11,id=isR?'R'+(i-10):'C'+(i+1),w=.62,h=1.05;passives.push(box(host.body,[w,h,.35],[x,y,-2.025],isR?black:ceramic,'Mini OLED '+id+' body'));for(const sy of[-1,1]){lands.push(box(host.body,[w+.15,.38,.035],[x,y+sy*.48,-2.1825],metal,'Mini OLED '+id+' PCB land'));terminations.push(box(host.body,[w+.035,.25,.37],[x,y+sy*.4,-2.015],metal,'Mini OLED '+id+' end termination'));}}
 return{pcb,ht,htPins,passives,terminations,lands};
}

/** Actual open white SMT HY2.0-4P; local +Z is the mating direction. */
function grove(host,face,id){
 const frame=new THREE.Group();frame.name='Mini OLED '+face+' open white Grove';frame.position.fromArray(spec.grove[face]);frame.quaternion.copy(FACE[face]);host.body.add(frame);
 const white=materials.plastic(0xeaeae3,{roughness:.64}),metal=materials.metal(0xb9b6a1,{roughness:.42}),walls=[],guides=[],contacts=[],returns=[],feet=[],lands=[];
 const floor=box(frame,[10.4,.7,7.1],[0,-2.225,-3.55],white,'Grove actual molded floor');
 for(const sx of[-1,1]){walls.push(box(frame,[.8,5.15,6.4],[sx*5.6,0,-3.2],white,'Grove tall side wall'));walls.push(box(frame,[.8,4.325,.7],[sx*5.6,-.4125,-6.75],white,'Grove lower inner seat sidewall'));guides.push(box(frame,[1.0,.55,3.9],[sx*4.7,2.3,-1.95],white,'Grove top insertion guide'));guides.push(box(frame,[.8,.55,1.0],[sx*4.7,-1.6,-.5],white,'Grove lower mouth retaining rail'));}
 const roof=box(frame,[8.6,.7,2.6],[0,2.225,-4.8],white,'Grove partial roof behind open top');
 const back=box(frame,[10.4,3.625,.6],[0,-.0625,-6.8],white,'Grove real recessed inner backing and panel seat');
 for(let i=0;i<4;i++){const x=(i-1.5)*2;contacts.push(box(frame,[.38,.38,4.9],[x,-.2,-3.85],metal,'Grove contact '+(i+1)));returns.push(box(frame,[.38,2.225,.38],[x,-1.3125,-6.3],metal,'Grove bent SMT terminal '+(i+1)));feet.push(box(frame,[.42,.15,2.15],[x,-2.5,-7.325],metal,'Grove SMT foot '+(i+1)));lands.push(box(frame,[.65,.035,2.35],[x,-2.5575,-7.325],metal,'Grove SMT solderland '+(i+1)));}
 const port=host.add(new Port({id,label:face==='left'?'Left Grove · I2C':'Right Grove · I2C',connector:'grove',position:spec.grove[face],quaternion:portQuaternion(face),hitSize:[12,1,5.15],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face,protocol:'I2C',scope:'Physical attachment only; no bus routing, electrical or SSD1315 behavior'}}));
 return{frame,floor,walls,guides,roof,back,contacts,returns,feet,lands,port};
}

function foldedFlex(host){
 const amber=materials.plastic(0xa97820,{roughness:.6,transparent:true,opacity:.91}),copper=materials.metal(0xb49439,{roughness:.48}),solder=materials.metal(0xc1c5bd,{roughness:.42});
 const tailShape=new THREE.Shape();tailShape.moveTo(-5.625,-2.1);tailShape.lineTo(5.625,-2.1);tailShape.lineTo(5.625,2.1);tailShape.lineTo(-5.625,2.1);tailShape.closePath();for(const[x,y]of spec.fpc.tailBoresMm)hole(tailShape,x,y,.4);
 const tail=solid(host.body,tailShape,.1,[0,0,-3.375],amber,'Mini OLED actual folded FPC solder tail with two open holes'),pads=[],fanTraces=[],foldTraces=[];
 for(let i=0;i<16;i++){const x=(i-7.5)*.65;pads.push(box(host.body,[.35,2.05,.175],[x,.8,-3.2875],solder,'Mini OLED FPC SMT contact '+(i+1)));fanTraces.push(ribbon(host.body,[{x,y:0,z:-3.335,width:.13,thickness:.012},{x:(i-7.5)*.32,y:-2.1,z:-3.335,width:.10,thickness:.012}],copper,'Mini OLED FPC fan trace '+(i+1)));}
 const path=[{y:-2.1,z:-3.325,width:6.8},{y:-3.0,z:-3.325,width:5.5},{y:-5.91,z:-3.325,width:5.5}];
 for(let i=1;i<=12;i++){const t=-Math.PI/2-i*Math.PI/24;path.push({y:-5.91+.16*Math.cos(t),z:-3.165+.16*Math.sin(t),width:5.5});}
 path.push({y:-6.07,z:1.915,width:5.5});
 for(let i=1;i<=12;i++){const t=Math.PI-i*Math.PI/24;path.push({y:-5.91+.16*Math.cos(t),z:1.915+.16*Math.sin(t),width:5.5});}
 path.push({y:-5.5,z:2.075,width:6.8});
 const folded=ribbon(host.body,path,amber,'Mini OLED installed closed folded FPC around PCB lower edge');
 for(let i=0;i<16;i++)foldTraces.push(ribbon(host.body,path.map(p=>({...p,x:(i-7.5)*.32,width:.10,thickness:.012})),copper,'Mini OLED folded embedded FPC trace '+(i+1)));
 const bond=box(host.body,[11.8,1.2,.1],[0,-4.9,2.075],amber,'Mini OLED FPC glass bond flange');
 return{tail,pads,fanTraces,folded,foldTraces,bond,path};
}

export function buildMiniOled(host){
 const board=pcb(host),left=grove(host,'left','grove'),right=grove(host,'right','grove-right'),flex=foldedFlex(host);
 const glassMat=materials.glossy(0x101b1b,{roughness:.24,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:1}),capMat=materials.glossy(0x071011,{roughness:.22,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:1});
 const base=box(host.body,[12,11,.7],[0,0,2.475],glassMat,'Mini OLED physical lower glass panel');
 const cap=box(host.body,[12,8,.55],[0,1.5,3.1],capMat,'Mini OLED physical upper cap glass and inactive border');
 const seal=box(host.body,[11.6,1.8,.4],[0,-4.45,3.025],materials.glossy(0x080d0d,{roughness:.4}),'Mini OLED COG seal on actual glass, no discrete controller package');
 const adhesive=box(host.body,[11,8.5,.05],[0,0,2.1],materials.plastic(0xd9d8c6,{roughness:.85}),'Mini OLED thin physical underside protection and adhesive seating');
 const display=host.add(new WhiteOledDisplay({id:'lcd',label:'0.42-inch 72×40 white Mini OLED',width:72,height:40,size:spec.display.activeMm,position:spec.display.position,offColor:0x071011,meta:{role:'external-framebuffer',monochrome:true,monochromeMapping:'Luminance threshold 0.5 to white at render time; raw source RGB bytes preserved',scope:'Externally written pixels only. No touch, I2C/SSD1315 commands, firmware or permanent image.'}}));
 host.miniOledAssembly={board,left,right,flex,glass:{base,cap,seal,adhesive},display};
 host.unitStickers=addStickers(host);
}
