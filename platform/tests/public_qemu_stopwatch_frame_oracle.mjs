// Observation only. This function is also serialized by Playwright into the
// page, so it deliberately has no module-scope dependencies or input effects.
export function stopwatchRedCircleOracle({frame=globalThis.uiflowRuntime?.lastFrame,summary=false}={}) {
  const result={pattern:'stopwatch-round-red-brightness255-v1',matches:false,
    expected:{width:466,height:466,center_x:233,center_y:233,radius:233,
      inside_rgb565:0xf800,outside_rgb565:0x0000,inside_pixels:170499,outside_pixels:46657}};
  if(!frame||frame.width!==466||frame.height!==466||frame.pixels?.length!==466*466*2){
    result.reason='physical-frame-dimensions-or-length';
    return summary?result:false;
  }
  let inside=0,outside=0,wrongInside=0,wrongOutside=0;
  for(let y=0;y<466;y++)for(let x=0;x<466;x++){
    const at=2*(y*466+x),color=frame.pixels[at]|frame.pixels[at+1]<<8;
    const visible=(x-233)*(x-233)+(y-233)*(y-233)<=233*233;
    if(visible){inside++;if(color!==0xf800)wrongInside++;}
    else{outside++;if(color!==0x0000)wrongOutside++;}
  }
  Object.assign(result,{inside_pixels:inside,outside_pixels:outside,
    wrong_inside_pixels:wrongInside,wrong_outside_pixels:wrongOutside});
  result.matches=inside===170499&&outside===46657&&wrongInside===0&&wrongOutside===0;
  return summary?result:result.matches;
}
