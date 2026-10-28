import*as THREE from'three';import{Display}from'../../core/index.js';import{spec}from'./dimensions.js';
/** Real visible128×56 pixels only. Controller memory/protocol stays external. */
export class TransparentOled extends Display{
 constructor(){super({id:'screen',label:'Transparent light-blue OLED · visible128×56',width:128,height:56,size:spec.display.size,position:spec.display.position,style:'oled',touch:false,glass:false,offColor:0,blackLevel:0,meta:{role:'external-framebuffer',monochrome:true,visiblePixels:[128,56],controllerMemory:[128,64],unmappedRows:8,unusedRowMapping:'Not asserted or emulated',pixelPitchMm:.274,pixelSizeMm:.254,frontAndRearEmission:true,scope:'Externally written visible pixels only; no SSD1309 registers,I2C,jumper/address logic,controller-memory mapping,power or automatic content.'}});
  for(const marker of['vec3 c = texture2D(map, (cell + 0.5) / res).rgb;','gl_FragColor = vec4(col, 1.0);'])if(!this.material.fragmentShader.includes(marker))throw new Error('Glass2 transparent OLED base shader marker changed;explicit product shader update required');
  this.material.transparent=true;this.material.depthWrite=false;this.material.toneMapped=false;
  this.material.fragmentShader=this.material.fragmentShader.replace('vec3 c = texture2D(map, (cell + 0.5) / res).rgb;','vec4 sourcePixel = texture2D(map, (cell + 0.5) / res);\n  vec3 c = vec3(step(0.5, dot(sourcePixel.rgb, vec3(0.2126, 0.7152, 0.0722))) * sourcePixel.a);');
  this.material.fragmentShader=this.material.fragmentShader.replace('gl_FragColor = vec4(col, 1.0);','float ink = clamp(max(col.r, max(col.g, col.b)), 0.0, 1.0);\n  gl_FragColor = vec4(vec3(0.18, 0.78, 1.0) * ink, ink);');
  this.panel.name='Glass2 front external transparent OLED pixel emission';this.panel.userData.role='emissive-pixel-overlay';
  // Separate opposing FrontSide planes preserve the actual mirrored rear view
  // and keep the glass a real translucent volume even when all pixels are off.
  this.rearPanel=new THREE.Mesh(this.panel.geometry.clone().rotateY(Math.PI),this.material);this.rearPanel.name='Glass2 rear mirrored transparent OLED pixel emission';this.rearPanel.position.z=-1.27;this.rearPanel.userData.role='emissive-pixel-overlay';this.object3d.add(this.rearPanel);
 }
}
