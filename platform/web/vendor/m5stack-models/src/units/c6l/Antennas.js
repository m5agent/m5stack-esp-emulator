import*as THREE from'three';import{Module,materials}from'../../core/index.js';import{mesh}from'../../modeling/parts.js';
const tau=Math.PI*2;
function ring(parent,outer,inner,depth,y,mat,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);const h=new THREE.Path();h.absarc(0,0,inner,0,tau,false);s.holes.push(h);return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:48}).rotateX(-Math.PI/2),mat,[0,y,0],name);}
function buildAntenna(host,lengthMm,label,url){const p=host.body,black=materials.plastic(0x1b1d1d,{roughness:.85}),rib=materials.plastic(0x292c2b,{roughness:.83}),gold=materials.metal(0xbdae74,{roughness:.43}),white=materials.plastic(0xe0dece,{roughness:.76});
 const nut=ring(p,4.2,3.2,8.0,-6,black,'C6L '+label+' real open RP-SMA coupling nut'),lip=ring(p,3.85,3.16,.55,-6,gold,'C6L '+label+' internal-thread metal mating lip');
 for(let i=0;i<44;i++){const a=i*tau/44;const o=mesh(p,new THREE.BoxGeometry(.13,6.9,.13),rib,[Math.cos(a)*4.18,-2.0,Math.sin(a)*4.18],'C6L '+label+' coupling knurl');o.rotation.y=-a;}
 class Thread extends THREE.Curve{getPoint(t,v=new THREE.Vector3()){const a=t*tau*6;return v.set(Math.cos(a)*3.205,-5.6+t*4.25,Math.sin(a)*3.205);}}
 const thread=mesh(p,new THREE.TubeGeometry(new Thread(),384,.06,6,false),gold,[0,0,0],'C6L '+label+' genuine internal helical thread');
 const dielectric=ring(p,3.18,.56,1.4,.3,white,'C6L '+label+' RP-SMA dielectric with centre opening'),contact=ring(p,.53,.25,3,-2.1,gold,'C6L '+label+' female hollow centre sleeve');
 const blind=mesh(p,new THREE.CylinderGeometry(.25,.25,.15,24),gold,[0,.9,0],'C6L '+label+' recessed female contact blind end');
 const base=mesh(p,new THREE.CylinderGeometry(4.0,3.95,9.5,48),black,[0,6.75,0],'C6L '+label+' closed rubber base');
 const band=mesh(p,new THREE.CylinderGeometry(4.035,4.035,4.0,64).rotateY(Math.PI),materials.plastic(0xe5e5df,{roughness:.85}),[0,6.4,0],'C6L '+label+' physical printed adhesive collar');band.userData={role:'physical-adhesive-collar',artworkKind:'reference-redraw',textureStatus:'disabled'};
 if(host.options.artwork!==false&&typeof window!=='undefined'&&typeof document?.createElementNS==='function'){const t=new THREE.TextureLoader().load(url,()=>{band.userData.textureStatus='ready';host.requestRender();},undefined,()=>{band.userData.textureStatus='error';host.requestRender();});t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=8;band.material.map=t;band.userData.textureStatus='pending';}
 const lower=mesh(p,new THREE.CylinderGeometry(3.8,4.0,14,48),black,[0,18.5,0],'C6L '+label+' fixed straight lower radome');
 const end=lengthMm-6,rodHeight=end-2.7-25.5;const rod=mesh(p,new THREE.CylinderGeometry(2.7,3.8,rodHeight,48),black,[0,25.5+rodHeight/2,0],'C6L '+label+' tapered solid rubber rod');const tip=mesh(p,new THREE.SphereGeometry(2.7,40,20,0,tau,0,Math.PI/2),black,[0,end-2.7,0],'C6L '+label+' closed rounded tip');
 for(const[y,r]of[[11.4,4.0],[25.5,3.8],[end-5.5,2.73]])mesh(p,new THREE.TorusGeometry(r,.055,6,48).rotateX(Math.PI/2),rib,[0,y,0],'C6L '+label+' observed molded seam');
 host.antennaAssembly={nut,lip,thread,dielectric,contact,blind,base,band,lower,rod,tip,lengthMm};
}
/** Exact supplied U202 accessories: straight source pose only; no inferred hinge API. */
export class LoraAntenna extends Module{static meta={id:'m5stack.unit.c6l.lora-antenna',name:'C6L supplied108mm LoRa RP-SMA antenna',sku:'U202 accessory',connector:'rp-sma-centre-pin',physicalConnector:'rp-sma-internal-thread-centre-socket',nominalLengthMm:108};build(){buildAntenna(this,108,'LoRa',new URL('./reference-redraw-lora-band.png',import.meta.url).href);}}
export class WifiAntenna extends Module{static meta={id:'m5stack.unit.c6l.wifi-antenna',name:'C6L supplied84mm Wi-Fi RP-SMA antenna',sku:'U202 accessory',connector:'rp-sma-centre-pin',physicalConnector:'rp-sma-internal-thread-centre-socket',nominalLengthMm:84};build(){buildAntenna(this,84,'Wi-Fi',new URL('./reference-redraw-wifi-band.png',import.meta.url).href);}}
