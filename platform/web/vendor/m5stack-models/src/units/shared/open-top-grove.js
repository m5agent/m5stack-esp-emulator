import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh} from '../../modeling/parts.js';

// Explicitly opted in by U029/U034/U135/U005/U016/U028. U016/U028 own drawings
// labels the 10 × 5.2 mm envelope. U005 uses the own CAD bay
// floor -1.2 to front +4 as an inferred 5.2 mm engineering envelope; this
// is not a labelled U005 connector dimension. The prior mouth height and Heart
// 10 mm width follow the official drawings; the open contour follows photos.
// Internal width, depth, wall and locking-tongue dimensions are appearance
// inferences, including clearance for this library's existing 8.4 mm plug.
export const OPEN_TOP_GROVE=Object.freeze({
 width:10,height:5.2,depth:6.5,wall:.7,innerWidth:8.6,upperOpeningWidth:6.8,
 lipWidth:.9,lipHeight:.8,contactTipDepth:.65,contactLength:1.2,
 tongue:Object.freeze({width:3.4,height:.65,depth:3,position:Object.freeze([0,1.2,-4.95])}),
});

export function refineOpenTopGrove(host,product){
 if(!['heart','rs485','encoder','angle','thermal','ncir'].includes(product))throw new Error('Open-top Grove requires an explicit U029/U034/U135/U005/U016/U028 product');
 const sockets=host.body.children.filter(o=>o.name==='HY2.0-4P');
 if(sockets.length!==1)throw new Error('Expected the original single Grove socket');
 const group=sockets[0],port=host.port('grove'),old=group.children;
 if(old.length!==12||old.some(o=>!o.isMesh))throw new Error('Unexpected base Grove geometry');
 const color=old[0].material.color.getHex(),geometries=new Set(),mats=new Set();
 for(const object of [...old]){geometries.add(object.geometry);mats.add(object.material);object.removeFromParent();}
 // The retired generic meshes share materials. Dispose each retired resource
 // once; new physical meshes each own their material under ComponentHost.
 for(const geometry of geometries)geometry.dispose();for(const material of mats)material.dispose();
 const d=OPEN_TOP_GROVE,label={heart:'Heart',rs485:'RS485',encoder:'Encoder',angle:'Angle',thermal:'Thermal',ncir:'NCIR'}[product],parts={};
 const box=(key,size,position,metal=false)=>{
  const material=metal?materials.metal(0xbaad83,{roughness:.42}):materials.plastic(color,{roughness:.58});
  const object=mesh(group,new THREE.BoxGeometry(...size),material,position,`${label} Grove ${key}`);parts[key]=object;return object;
 };
 // Continuous side walls provide the two visible upper rails. No plane spans
 // the open upper channel, and the short central tongue joins the rear wall.
 for(const sign of [-1,1])box(`side rail ${sign<0?'left':'right'}`,[d.wall,d.height,d.depth],[sign*(d.width-d.wall)/2,0,-d.depth/2]);
 // A narrow top slot sits above the wider lower mating channel. Its raised
 // lips clear the unchanged plug nose; the visible metal is a short end,
 // not a long exposed bar running all the way to the rear web.
 for(const sign of [-1,1])box(`upper lip ${sign<0?'left':'right'}`,[d.lipWidth,d.lipHeight,d.depth],[sign*(d.upperOpeningWidth+d.lipWidth)/2,(d.height-d.lipHeight)/2,-d.depth/2]);
 box('floor',[d.innerWidth,d.wall,d.depth],[0,-(d.height-d.wall)/2,-d.depth/2]);
 box('rear wall',[d.innerWidth,d.height,.6],[0,0,-d.depth+.3]);
 // Photos show same-colored material behind the short contact row. This
 // recessed support is a reconstruction of that visible inner floor, not
 // a claim about an independently specified connector component.
 const contactRear=d.contactTipDepth+d.contactLength,supportDepth=d.depth-contactRear;
 box('recessed contact support',[d.innerWidth,2.7,supportDepth],[0,-1.25,-contactRear-supportDepth/2]);
 box('short locking tongue',[d.tongue.width,d.tongue.height,d.tongue.depth],d.tongue.position);
 for(const sign of [-1,1])box(`mouth ear ${sign<0?'left':'right'}`,[d.wall,1.1,.6],[sign*(d.width-d.wall)/2,d.height/2-.55,0]);
 for(let i=0;i<4;i++)box(`contact ${i+1}`,[.42,.42,d.contactLength],[(i-1.5)*2,-.15,-d.contactTipDepth-d.contactLength/2],true);
 group.userData={...group.userData,visualFamily:'open-top-grove',product,dimensionsMm:d,scope:'Physical appearance only; inferred internal dimensions are not connector manufacturing tolerances.'};
 host.groveSocketAssembly={group,port,parts,dimensions:d};
 return host.groveSocketAssembly;
}
