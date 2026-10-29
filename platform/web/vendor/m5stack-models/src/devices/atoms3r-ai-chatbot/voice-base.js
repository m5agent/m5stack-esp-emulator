/** MIT. Atomic Voice Base mating assembly. Native shells come from each exact kit, never from a neighbouring host. */
import * as T from 'three';
import {Port,materials} from '../../core/index.js';
import {slab,mesh,header,FACE,portQuaternion} from '../../modeling/parts.js';
import {printedArtwork} from '../../modeling/artwork.js';
const decode=(s,C)=>new C(Uint8Array.from(atob(s),c=>c.charCodeAt(0)).buffer);
export function buildVoiceBase(host,{data,rearZ,sourceMatingZ,sourceXY=[0,0],assembledInsertionMm=2.0,artwork}){
 const existing=new Set();host.body.traverse(o=>existing.add(o.id));const a=host.voiceBaseAssembly={nativeParts:{},matingPlaneZ:rearZ,shellDepthMm:10,documentedOverallMm:14.14,documentedUnmatedPinProjectionMm:4.14,pinBodyLengthMm:4.14,insertionMm:assembledInsertionMm,assembledInsertionMm},shift=[-sourceXY[0],-sourceXY[1],rearZ-sourceMatingZ],bottomZ=rearZ-10;
 for(const p of data){const g=new T.BufferGeometry();for(const [k,C,n]of[['position',Float32Array,3],['normal',Float32Array,3],['sourceFaceIndex',Uint32Array,1],['sourceAttributeWord',Uint16Array,1]])g.setAttribute(k,new T.BufferAttribute(decode(p[k],C),n));g.setIndex(new T.BufferAttribute(decode(p.index,Uint32Array),1));g.computeBoundingBox();const o=mesh(host.body,g,materials.plastic(0x5a5e5c,{roughness:.78}),shift,'Own kit native '+p.id);o.userData={role:'physical-assembly',source:'official-own-kit-native',sourceComponent:p.sourceComponent,sourceFaces:p.faces};a.nativeParts[p.id]=o;}
 const plate=(w,h,d,r,p,m,name,holes=[])=>{const o=slab(host.body,w,h,d,r,p,m,holes,.025);o.name=name;o.userData.role='physical-assembly';return o;};
 const black=materials.plastic(0x1a2220,{roughness:.9}),green=materials.plastic(0x244f3c,{roughness:.9});
 // Hidden audio board follows the native case's rounded/corner support clearances.
 // The full board span is retained; four corners clear molded posts instead of
 // reducing the entire PCB or the documented 2014 speaker footprint.
 const boardShape=new T.Shape(),w=10.1,h=10.1,c=3.1;boardShape.moveTo(-w+c,-h);boardShape.lineTo(w-c,-h);boardShape.lineTo(w,-h+c);boardShape.lineTo(w,h-c);boardShape.lineTo(w-c,h);boardShape.lineTo(-w+c,h);boardShape.lineTo(-w,h-c);boardShape.lineTo(-w,-h+c);boardShape.closePath();
 for(const [x,y,count]of[[7.62,-2.7,5],[-7.62,-3.97,4]])for(let i=0;i<count;i++){const hole=new T.Path();hole.absarc(x,y+(i-(count-1)/2)*2.54,.42,0,Math.PI*2,true);boardShape.holes.push(hole);}
 a.pcb=mesh(host.body,new T.ExtrudeGeometry(boardShape,{depth:.8,bevelEnabled:false,curveSegments:20}),green,[0,0,rearZ-(data.length>1?3.35:1.5)],'Voice Base actual corner-cleared audio PCB with real contact bores');a.pcb.userData.role='physical-assembly';
 // 2014 refers to the actual 20x14mm front metal footprint. Its acoustic back
 // chamber is a separate smaller package; corner radii and hidden seats are
 // appearance inferences constrained by this exact native case.
 a.speaker=new T.Group();a.speaker.name='Voice Base 2014 speaker physical package';a.speaker.userData={nominalEnvelopeMm:[20,14,4.4],hiddenDimensions:'appearance-inferred independent frame/chamber/corner clearance'};host.body.add(a.speaker);
 const speakerPart=(width,height,depth,radius,pos,mat,name,holes=[])=>{const o=slab(a.speaker,width,height,depth,radius,pos,mat,holes,.025);o.name=name;o.userData.role='physical-assembly';return o;};
 a.speakerChamber=speakerPart(18.3,12.3,4.1,3.6,[0,-3.2,bottomZ+1.85],black,'Voice Base 2014 speaker actual acoustic back chamber');
 a.speakerFrame=speakerPart(20,14,.3,2.3,[0,-3.2,bottomZ+5.95],materials.metal(0x89918a,{roughness:.61}),'Voice Base 2014 actual 20x14mm rounded metal frame',[{w:15.9,h:9.9,r:1.5}]);
 a.speakerDiaphragm=speakerPart(15.8,9.8,.18,1.5,[0,-3.2,bottomZ+5.97],materials.metal(0x626d65,{roughness:.86}),'Voice Base actual recessed speaker diaphragm');
 for(const x of[-9.4,9.4])plate(.65,4.8,3.6,.2,[x,-3.4,bottomZ+1.55],black,'Voice Base fixed side speaker retaining seat');
 a.microphone=plate(3.2,2.5,1,.2,[0,9.1,rearZ-2.6],materials.metal(0xb3b5ab),'Voice Base passive microphone package');
 for(const [x,y]of[[5,4],[4,-7]])plate(3.5,3.5,.7,.2,[x,y,rearZ-2.2],black,'Voice Base concealed audio IC envelope');
 // Official unassembled overall height:10mm shell+4.14mm projecting contacts.
 // In this assembled appearance model each full4.14mm metal body is partly
 // buried in the base;the inferred tip stops before the actual host socket floor.
 a.contactPins=[];for(const [x,y,count]of[[7.62,-2.70,5],[-7.62,-3.97,4]])for(let i=0;i<count;i++)a.contactPins.push(mesh(host.body,new T.BoxGeometry(.55,.55,4.14),materials.metal(0xbca676,{roughness:.4}),[x,y+(i-(count-1)/2)*2.54,rearZ+assembledInsertionMm-2.07],'Voice Base fully mated 2.54mm contact pin'));
 a.pcbTailVisualLengthMm=data.length>1?1.25:0;if(data.length>1)for(const p of a.contactPins)plate(.5,.5,1.25,.02,[p.position.x,p.position.y,rearZ-3.35],materials.metal(0xbca676,{roughness:.4}),'Voice Base CAM cover-through hidden PCB solder tail');
 a.expansion=header(host.body,{position:[-7.62,-4,bottomZ+.06],face:'back',cols:1,rows:5,pitch:2.0});
 host.add(new Port({id:'voice-base-ext',label:'Voice Base exposed 5P expansion · visual',connector:'m5.voice-base.ext-5p',position:[-7.62,-4,bottomZ],quaternion:portQuaternion('back'),hitSize:[3,1,12],meta:{role:'visual-connector',pitchMm:2.0,pitchSource:'Own native opening and own-photo inferred fit;no rated pinout or tolerance claim',source:'Own A149 drawing/photo;no bus or audio emulation'}}));
 a.label=plate(15.2,20.5,.08,.3,[2.3,0,bottomZ-.08],materials.plastic(0xe4e4df,{roughness:.85}),'Voice Base actual bottom adhesive film');
 a.sideLabels=[];
 for(const [file,face,y]of[['base-front','bottom',-12],['base-mic','top',12]]){const g=new T.Group();g.position.set(0,y,rearZ-5);g.quaternion.copy(FACE[face]);g.name='Voice Base physical '+file+' adhesive film';host.body.add(g);const o=slab(g,14.5,5.7,.08,.2,[0,0,0],materials.plastic(0xddddda,{roughness:.85}),[],.015);o.name=g.name+' substrate';o.userData.role='physical-label-substrate';a.sideLabels.push(o);printedArtwork(host,{target:o,url:artwork[file],size:[14.5,5.7],position:[0,y,rearZ-5],face,depth:.2,artworkKind:'official-raster',name:'Approved ordinary PNG · '+file});}
 printedArtwork(host,{target:a.label,url:artwork['base-bottom'],size:[15.2,20.5],position:[2.3,0,bottomZ-.08],face:'back',depth:.2,artworkKind:'official-raster',name:'Approved ordinary PNG · Voice Base bottom pin/spec artwork'});
 a.inferredMeshes=[];host.body.traverse(o=>{if(o.isMesh&&!existing.has(o.id)&&o.userData.role!=='printed-artwork'&&o.userData.source!=='official-own-kit-native'&&[].concat(o.material).some(m=>m.opacity!==0))a.inferredMeshes.push(o);});
 return a;
}
