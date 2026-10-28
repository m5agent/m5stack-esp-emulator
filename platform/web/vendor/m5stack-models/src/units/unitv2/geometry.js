import*as THREE from'three';import{materials}from'../../core/index.js';import{mesh,FACE,portQuaternion}from'../../modeling/parts.js';import{roundedRect,capsule}from'../../core/geometry.js';
export{THREE,mesh,FACE,portQuaternion,roundedRect,capsule};export const tau=Math.PI*2,plastic=(c=0x1c201e)=>materials.plastic(c,{roughness:.76}),metal=(c=0xb7b9b3)=>materials.metal(c,{roughness:.4});
export const box=(p,s,at,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,at,n);
export const solid=(p,s,d,at,m,n)=>mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:48}),m,at,n);
export const hole=(s,x,y,r)=>{const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);return h;};
export function annulus(p,ro,ri,d,at,m,n){const s=new THREE.Shape();s.absarc(0,0,ro,0,tau,false);hole(s,0,0,ri);return solid(p,s,d,at,m,n);}
export function frame(parent,name,at=[0,0,0],face=null){const g=new THREE.Group();g.name=name;g.position.fromArray(at);if(face)g.quaternion.copy(FACE[face]);parent.add(g);return g;}
export function segment(p,a,b,r,m,n){const av=new THREE.Vector3(...a),bv=new THREE.Vector3(...b),v=bv.clone().sub(av),o=mesh(p,new THREE.CylinderGeometry(r,r,v.length(),20),m,av.add(bv).multiplyScalar(.5).toArray(),n);o.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),v.normalize());return o;}
/** Closed tube: real capped material ends, without a transparent cover across its route. */
export function tube(parent,curve,r,segments,m,name){const g=new THREE.TubeGeometry(curve,segments,r,12,false),p=Array.from(g.attributes.position.array),ind=Array.from(g.index.array);for(const[end,ring]of[[0,0],[1,segments]]){const c=curve.getPointAt(end),ci=p.length/3;p.push(c.x,c.y,c.z);for(let j=0;j<12;j++){const a=ring*13+j,b=a+1;if(end)ind.push(ci,b,a);else ind.push(ci,a,b);}}g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));g.setIndex(ind);g.computeVertexNormals();return mesh(parent,g,m,[0,0,0],name);}
