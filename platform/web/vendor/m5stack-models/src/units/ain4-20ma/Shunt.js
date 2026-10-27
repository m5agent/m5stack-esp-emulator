import*as THREE from'three';import{Module,Port,materials}from'../../core/index.js';import{mesh}from'../../modeling/parts.js';
/** Two real sockets in a removable two-pin cap. No power-mode or signal state. */
export class Shunt extends Module{
 static meta={id:'m5stack.unit.ain4-20ma.shunt',name:'U162 removable two-pin jumper cap',sku:'U162 accessory',connector:'pin-header-2.54-2p'};
 build(){const s=new THREE.Shape();s.moveTo(-2.54,-1.15);s.lineTo(2.54,-1.15);s.lineTo(2.54,1.15);s.lineTo(-2.54,1.15);s.closePath();for(const x of[-1.27,1.27]){const p=new THREE.Path();p.absarc(x,0,.48,0,Math.PI*2,false);s.holes.push(p);}const plastic=materials.plastic(0x1b1d1a,{roughness:.75}),metal=materials.metal(0xb9a467,{roughness:.47});const body=mesh(this.body,new THREE.ExtrudeGeometry(s,{depth:2.4,bevelEnabled:false,curveSegments:32}).rotateX(-Math.PI/2),plastic,[0,0,0],'AIN4-20mA shunt two physical blind mating bores');const cap=mesh(this.body,new THREE.BoxGeometry(5.08,.3,2.3),plastic,[0,2.55,0],'AIN4-20mA shunt closed molded top');const contacts=[];for(const x of[-1.27,1.27])for(const side of[-1,1])contacts.push(mesh(this.body,new THREE.BoxGeometry(.1,2.05,.48),metal,[x+side*.34,1.28,0],'AIN4-20mA shunt recessed spring contact'));mesh(this.body,new THREE.BoxGeometry(3.55,.15,.48),metal,[0,2.325,0],'AIN4-20mA shunt internal physical bridge');this.shuntAssembly={body,cap,contacts};}
}
/** Reserves shared physical pins so two solid caps cannot occupy the same pin. */
export class JumperPort extends Port{
 constructor(options){super(options);this.physicalPins=options.meta.physicalPins;}
 attach(module,options={}){for(const c of this.host.components.values())if(c instanceof JumperPort&&c!==this&&c.module&&c.module!==module&&c.physicalPins.some(p=>this.physicalPins.includes(p)))throw new Error(`Jumper position ${this.id} shares a physical pin with occupied ${c.id}`);return super.attach(module,options);}
}
