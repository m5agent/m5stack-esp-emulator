import * as THREE from 'three';
import {Display} from '../core/components/Display.js';
/** Reflective paper surface. It accepts external pixels; no waveform, palette or refresh simulation. */
export class PaperDisplay extends Display {
 constructor(options){super({...options,style:'flat',pixelEffect:false,blackLevel:0,glass:false});
  // Texture transform corrects top-left raster orientation without changing hit-test UV coordinates.
  this.texture.repeat.set(1,-1);this.texture.offset.set(0,1);this.texture.updateMatrix();
  this.surfaceMaterial=new THREE.MeshStandardMaterial({map:this.texture,color:0xffffff,roughness:.97,metalness:0});
  this.panel.material=this.surfaceMaterial;this.fill('#e4e2d7');
 }
 dispose(){this.material.dispose();super.dispose();}
}
