import * as THREE from 'three';
import {mergeVertices,toCreasedNormals} from 'three/addons/utils/BufferGeometryUtils.js';

// Consistent CCW loops preserve outward winding on the solid outer walls,
// inward cavity walls and the sculpted cap's genuine open lower rim.
function ring(w,h,r,z){
 const points=[],corners=[[w/2-r,h/2-r,0],[-w/2+r,h/2-r,Math.PI/2],[-w/2+r,-h/2+r,Math.PI],[w/2-r,-h/2+r,Math.PI*1.5]];
 for(const [x,y,start]of corners)for(let i=0;i<=10;i++){const a=start+i*Math.PI/20;points.push(new THREE.Vector3(x+r*Math.cos(a),y+r*Math.sin(a),z));}
 return points;
}
function triangle(values,a,b,c){for(const p of [a,b,c])values.push(p.x,p.y,p.z);}
function wall(values,a,b,inward=false){
 for(let i=0;i<a.length;i++){const j=(i+1)%a.length;if(inward){triangle(values,a[i],b[j],a[j]);triangle(values,a[i],b[i],b[j]);}else{triangle(values,a[i],a[j],b[j]);triangle(values,a[i],b[j],b[i]);}}
}
function rim(values,outer,inner,down=false){
 for(let i=0;i<outer.length;i++){const j=(i+1)%outer.length;if(down){triangle(values,outer[i],inner[j],outer[j]);triangle(values,outer[i],inner[i],inner[j]);}else{triangle(values,outer[i],outer[j],inner[j]);triangle(values,outer[i],inner[j],inner[i]);}}
}
function fan(values,loop,center,down=false){for(let i=0;i<loop.length;i++){const j=(i+1)%loop.length;if(down)triangle(values,loop[i],center,loop[j]);else triangle(values,loop[i],loop[j],center);}}
function geometry(values){let g=new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(values,3));g=mergeVertices(toCreasedNormals(g,.72),.00001);g.computeBoundingBox();g.computeBoundingSphere();return g;}

/** Photo-derived 1U red cap: tapered shoulders, concave top and open underside. */
export function keycapGeometry(){
 const values=[],outer=[ring(18.6,18.6,.65,0),ring(19.0,19.0,.8,.28),ring(14.0,14.0,1.15,8.9),ring(13.5,13.5,1.3,10)],inner=[ring(16.8,16.8,.55,0),ring(11.2,11.2,.8,7.1)];
 for(let i=0;i+1<outer.length;i++)wall(values,outer[i],outer[i+1]);
 wall(values,inner[0],inner[1],true);rim(values,outer[0],inner[0],true);fan(values,inner[1],new THREE.Vector3(0,0,7.1),true);
 // The highest rim is 20.3 mm in the assembled product; the center dish is
 // 0.4 mm lower. There is no photographic patch or floating planar top.
 let previous=outer.at(-1);for(const fraction of [.8,.6,.4,.2]){const next=ring(13.5*fraction,13.5*fraction,1.3*fraction,9.6+.4*fraction*fraction);rim(values,previous,next);previous=next;}fan(values,previous,new THREE.Vector3(0,0,9.6));
 return geometry(values);
}

/** A real-thickness transparent switch enclosure with a clear inner chamber. */
export function switchWallGeometry(){
 const values=[],outer=[ring(14.6,14.6,.75,4.35),ring(14.6,14.6,.75,6.1),ring(12.6,12.6,.8,9.25)],inner=[ring(13,13,.35,4.35),ring(13,13,.35,5.8),ring(10.9,10.9,.4,9.25)];
 for(let i=0;i+1<outer.length;i++){wall(values,outer[i],outer[i+1]);wall(values,inner[i],inner[i+1],true);}rim(values,outer[0],inner[0],true);rim(values,outer.at(-1),inner.at(-1));return geometry(values);
}
