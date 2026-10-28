import{Module}from'../../core/index.js';
import{THREE,hexShape,mesh}from'./geometry.js';
import{spec}from'./dimensions.js';
/** Removable supplied sheet placement,not a fabricated plug/latch or hinge. */
export class Diffuser extends Module{static meta={id:'m5stack.unit.neohex.diffuser',name:'NeoHEX supplied opal light sheet',connector:spec.diffuser.connector,physicalRole:'independent-removable-sheet',scope:'Static actual sheet with inferred thickness/seat;no joints or optical calibration'};build(){const geometry=new THREE.ExtrudeGeometry(hexShape(),{depth:spec.diffuser.thicknessMm,bevelEnabled:false,curveSegments:32}).rotateX(-Math.PI/2),sheet=mesh(this.body,geometry,new THREE.MeshPhysicalMaterial({color:0xf3f3ed,roughness:.58,transparent:true,opacity:.37,transmission:.25,thickness:.3,ior:1.45,depthWrite:false}),[0,0,0],'NeoHEX actual independent opal hexagonal diffuser resting on37 package tops');sheet.userData={role:'physical-diffuser',thicknessInferred:true,scope:'Separate supplied light sheet;no fake film/support socket or calibrated optics'};this.diffuserAssembly={sheet};}}
export default Diffuser;
