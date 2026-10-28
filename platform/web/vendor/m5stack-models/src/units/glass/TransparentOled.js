import*as THREE from'three';import{Display}from'../../core/index.js';import{spec}from'./dimensions.js';
/** Visible pixels are external. No controller row mapping, firmware or touch. */
export class TransparentOled extends Display{
 constructor(){super({id:'screen',label:'U158 transparent blue OLED · 128×56',width:128,height:56,size:spec.display.size,position:spec.display.position,style:'oled',touch:false,glass:false,offColor:0,blackLevel:0,meta:{role:'external-framebuffer',monochrome:true,visiblePixels:[128,56],activeAreaMm:[35.05,15.32],pitchMm:.274,dotMm:.254,source:'Own panel datasheet pages4/5; website18mm conflicts',controllerMatrixDocumented:[128,64],controllerMapping:'Not implemented or asserted',scope:'External visible pixels only; no touch,SSD1309,I2C,firmware or permanent content'}});
  this.material.transparent=true;this.material.depthWrite=false;this.material.toneMapped=false;
  this.material.uniforms.activeMm={value:new THREE.Vector2(...spec.display.size)};
  this.material.fragmentShader=`uniform sampler2D map;uniform vec2 res;uniform vec2 activeMm;uniform float brightness;uniform float effect;varying vec2 vUv;
void main(){
 // Native square 0.274mm pitch; rounded drawing AA leaves 0.002/0.004mm residual.
 vec2 mm=vec2(vUv.x,1.0-vUv.y)*activeMm;vec2 p=(mm+vec2(0.01))/0.274;vec2 cell=clamp(floor(p),vec2(0.0),res-1.0);
 vec4 sourcePixel=texture2D(map,(cell+0.5)/res);float bit=step(0.5,dot(sourcePixel.rgb,vec3(0.2126,0.7152,0.0722)));
 vec2 f=fract(p);vec2 fw=max(fwidth(p),vec2(0.00001));vec2 halfGap=vec2((0.274-0.254)/0.548);
 vec2 mask=smoothstep(halfGap-fw,halfGap+fw,f)*(vec2(1.0)-smoothstep(vec2(1.0)-halfGap-fw,vec2(1.0)-halfGap+fw,f));
 float detail=effect*(1.0-smoothstep(0.25,0.5,max(fw.x,fw.y)));float ink=bit*sourcePixel.a*clamp(brightness,0.0,1.0)*mix(1.0,mask.x*mask.y,detail);
 gl_FragColor=vec4(vec3(0.18,0.78,1.0)*ink,ink);#include <colorspace_fragment>
}`.replace(';#include',';\n#include');
  this.panel.name='Glass front external transparent blue pixel emission';this.panel.userData.role='emissive-pixel-overlay';this.panel.renderOrder=4;
  // Same world XY and UV; reverse triangles, not UV. Looking through the back
  // therefore mirrors the physical front content instead of making it readable.
  const g=this.panel.geometry.clone(),ix=g.index;for(let i=0;i<ix.count;i+=3){const b=ix.getX(i+1);ix.setX(i+1,ix.getX(i+2));ix.setX(i+2,b);}g.computeVertexNormals();
  this.rearPanel=new THREE.Mesh(g,this.material);this.rearPanel.name='Glass physically mirrored rear external pixel emission';this.rearPanel.userData.role='emissive-pixel-overlay';this.rearPanel.position.z=spec.display.rearZ-spec.display.position[2];this.rearPanel.renderOrder=4;this.object3d.add(this.rearPanel);
 }
 setStyle(value){if(value!=='oled')throw new Error('Glass has a fixed transparent blue OLED style');return super.setStyle('oled');}
 setTouchEnabled(value){if(value!==false)throw new Error('Glass has no touch input');return super.setTouchEnabled(false);}
 touch(){throw new Error('Glass has no touch input');}
 onPointerDown(){}onPointerMove(){}onPointerUp(){}onPointerCancel(){}
 handle(cmd){if(cmd.type==='display'){if(cmd.touch!=null&&cmd.touch!==false)throw new Error('Glass has no touch input');if(cmd.style!=null&&cmd.style!=='oled')throw new Error('Glass has a fixed transparent blue OLED style');}return super.handle(cmd);}
}
