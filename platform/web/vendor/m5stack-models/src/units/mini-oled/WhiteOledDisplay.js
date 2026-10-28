import{Display}from'../../core/index.js';
/** Existing visual framebuffer contract with the actual fixed white OLED appearance. */
export class WhiteOledDisplay extends Display{
 constructor(options){super({...options,style:'oled',touch:false,blackLevel:0,glass:false});const marker='vec3 c = texture2D(map, (cell + 0.5) / res).rgb;';if(this.material.fragmentShader.split(marker).length!==2)throw new Error('Mini OLED framebuffer shader marker changed');this.material.fragmentShader=this.material.fragmentShader.replace(marker,'vec3 c = vec3(step(0.5, dot(texture2D(map, (cell + 0.5) / res).rgb, vec3(0.2126, 0.7152, 0.0722))));');this.panel.userData.role='display-surface';this.panel.renderOrder=3;}
 setStyle(value){if(value!=='oled')throw new Error('Mini OLED has a fixed white OLED pixel style');return super.setStyle('oled');}
 setTouchEnabled(value){if(value!==false)throw new Error('Mini OLED has no touch input');return super.setTouchEnabled(false);}
 touch(){throw new Error('Mini OLED has no touch input');}
 onPointerDown(){}onPointerMove(){}onPointerUp(){}onPointerCancel(){}
 handle(cmd){if(cmd.type==='display'){if(cmd.touch!=null&&cmd.touch!==false)throw new Error('Mini OLED has no touch input');if(cmd.style!=null&&cmd.style!=='oled')throw new Error('Mini OLED has a fixed white OLED pixel style');}return super.handle(cmd);}
}
