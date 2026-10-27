import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,portQuaternion} from '../../modeling/parts.js';
import {unitPcb,connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';

/** Appearance only. The native full shell closes the product, independently of artwork. */
export function buildGps(host){
 addCadParts(host,data,{shell:materials.plastic(0xe3e6df,{roughness:.8})});
 const pcb=unitPcb(host.body,{h:48});pcb.name='GPS v1.1 PCB with Grove and mounting clearances';
 // The official product documents an internal ceramic antenna. These concealed
 // solids convey package depth only: no undocumented trace layout or RF model.
 const ceramic=slab(host.body,17,17,1.7,.35,[0,10,.95],materials.plastic(0xd7c7a5,{roughness:.9}),[],.08);
 ceramic.name='GPS concealed ceramic antenna envelope';
 ceramic.userData={role:'inferred-hidden-package',scope:'Visual envelope only; exact hidden package size and placement unconfirmed'};
 const receiver=slab(host.body,10,9,1.3,.18,[0,7,-1.2],materials.metal(0xa6ada9,{roughness:.55}),[],.06);
 receiver.name='GPS concealed receiver shield envelope';
 receiver.userData={role:'inferred-hidden-package',part:'ATGM336H-6N documented by product page',scope:'No circuit, RF, GNSS, firmware or electrical simulation'};
 const socket=connector(host.body,48,true,{height:5.2});socket.name='GPS cyan open-top HY2.0-4P';
 // shared connector uses one plastic material; color it directly rather than
 // introducing a sheet across the open mating channel.
 socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'UART',pinReference:'Official HY2.0-4P cable colors; UART names follow product table. Port metadata only.',scope:'Physical mating and external cable pose only; no UART or GNSS behavior'}}));
 screw(host.body,[0,spec.mountY,-3.97],'back',1.4);
 // A short concealed shank terminates inside the housing; the real two LEGO
 // bores and the board's matching clearances remain open through the assembly.
 mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.2,24).rotateX(Math.PI/2),materials.metal(0x8e9796),[0,spec.mountY,-2.5],'GPS concealed mounting screw shank');
 host.add(new Component({id:'sensor',label:'GPS v1.1 appearance anchor',meta:{role:'visual-anchor',scope:'No position, satellite, UART, NMEA, timing or electrical behavior'}}));
 host.gpsAssembly={pcb,ceramic,receiver,socket,port};
 host.unitStickers=addStickers(host);
}
