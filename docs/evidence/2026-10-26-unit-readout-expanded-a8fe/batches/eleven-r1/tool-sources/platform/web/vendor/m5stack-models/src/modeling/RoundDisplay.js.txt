import * as THREE from 'three';
import {Display} from '../core/components/Display.js';
/** Circular visible area with square framebuffer UVs; no runtime or display-driver emulation. */
export class RoundDisplay extends Display {
 constructor({diameter,...options}){super({...options,size:[diameter,diameter]});this.panel.geometry.dispose();this.panel.geometry=new THREE.CircleGeometry(diameter/2,128);if(this.glass){this.glass.geometry.dispose();const size=options.glass?.size?.[0]??diameter;this.glass.geometry=new THREE.CircleGeometry(size/2,128);}}
}
