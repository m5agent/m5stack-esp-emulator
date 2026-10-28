import {materials} from '../../core/index.js';
import {THREE,mesh,hole,solid,box} from './geometry.js';
import {spec} from './dimensions.js';
import {contactDrills} from './connectors.js';
export function electronics(host){const dark=materials.plastic(0x181c1b,{roughness:.85}),metal=materials.metal(0xadb5a7,{roughness:.43}),drills=contactDrills();
 // Upstream returns terminate in a supported lower PCB tongue,not empty air.
 const boardBottom=-16.8,boardTop=22.7,shape=new THREE.Shape();shape.moveTo(-10.1,-7.5);shape.lineTo(-4.8,-7.5);shape.lineTo(-4.8,boardBottom);shape.lineTo(4.8,boardBottom);shape.lineTo(4.8,-7.5);shape.lineTo(10.1,-7.5);shape.lineTo(10.1,boardTop);shape.lineTo(-10.1,boardTop);shape.closePath();for(const[i,p]of drills.entries())hole(shape,p.x,p.y,.35,i*.017);hole(shape,0,-12,2.05);
 const pcb=mesh(host.body,solid(shape,.8),dark,[0,0,0],'PbHub original actual black PCB and inferred retained input tongue;28real drills'),lands=[],solder=[];for(const p of drills){const annulus=new THREE.Shape();annulus.absarc(p.x,p.y,.53,0,Math.PI*2,false);hole(annulus,p.x,p.y,.35);lands.push(mesh(host.body,solid(annulus,.04),metal,[0,0,.8],'PbHub actual plated contact land '+p.id+'/'+p.pin));solder.push(mesh(host.body,solid(annulus,.04),metal,[0,0,-.04],'PbHub actual rear solder annulus '+p.id+'/'+p.pin));}
 const mcu=box(host.body,[5.2,5.2,1],[0,2.6,1.3],dark,'PbHub own visible QFP32 package;manufacturer model unresolved'),leads=[];for(const axis of[0,1])for(const sign of[-1,1])for(let i=0;i<8;i++){const along=(i-3.5)*.6;leads.push(box(host.body,axis?[.28,.8,.2]:[.8,.28,.2],axis?[along,2.6+sign*2.85,.9]:[sign*2.85,2.6+along,.9],metal,'PbHub QFP32 actual four-sided lead'));}
 const crystal=box(host.body,[4.8,3.2,1.4],[0,12.5,1.5],materials.metal(0x939a92,{roughness:.3}),'PbHub own upper metal crystal envelope'),crystalFeet=[];for(const sign of[-1,1])crystalFeet.push(box(host.body,[1.1,1.7,.15],[sign*2.7,12.5,.875],metal,'PbHub actual crystal solder foot'));
 const passives=[],ends=[];for(const[x,y,w,h,col]of[[-3,8.1,1.1,1.9,0x8e8260],[0,8.1,1.1,1.9,0x343a33],[3,8.1,1.1,1.9,0x8e8260],[-3.4,15.3,1.3,1.7,0x8e8260],[3.4,15.3,1.3,1.7,0x8e8260],[-3.4,-4.9,1.2,1.7,0x343a33],[0,-4.9,1.2,1.7,0x343a33],[3.4,-4.9,1.2,1.7,0x343a33]]){passives.push(box(host.body,[w,h,.55],[x,y,1.075],materials.plastic(col,{roughness:.8}),'PbHub own visible fixed passive'));for(const sign of[-1,1])ends.push(box(host.body,[w,.3,.58],[x,y+sign*(h-.25)/2,1.09],metal,'PbHub retained passive termination'));}
 return{pcb,drills,lands,solder,mcu,leads,crystal,crystalFeet,passives,ends};
}
