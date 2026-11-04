// Observation only; Playwright serializes this function without module scope.
// m5_epd_panel.c's Spectra6 index 3 is ARGB 0xffbf0000. QEMU's
// PIXMAN_r5g6b5 shared-frame conversion yields (0xbf >> 3) << 11 = 0xb800.
export function papercolorRedFrameOracle({frame=globalThis.uiflowRuntime?.lastFrame,
  afterSequence=0,afterSourceSequence=0,summary=false}={}) {
  const result={pattern:'papercolor-spectra6-red-v1',matches:false,
    expected:{width:400,height:600,rgb888:0xbf0000,rgb565:0xb800,pixels:240000},
    after_sequence:afterSequence,after_source_sequence:afterSourceSequence};
  if(!frame||frame.width!==400||frame.height!==600||frame.format!=='rgb565le'
    ||frame.pixels?.length!==480000){
    result.reason='physical-frame-dimensions-format-or-length';
    return summary?result:false;
  }
  if(!Number.isSafeInteger(afterSequence)||afterSequence<0||!Number.isSafeInteger(afterSourceSequence)||afterSourceSequence<0
    ||!Number.isSafeInteger(frame.sequence)||frame.sequence<=afterSequence
    ||!Number.isSafeInteger(frame.sourceSequence)||frame.sourceSequence<=afterSourceSequence){
    result.reason='fresh-frame-required';
    return summary?result:false;
  }
  let red=0;
  for(let at=0;at<frame.pixels.length;at+=2)
    if((frame.pixels[at]|frame.pixels[at+1]<<8)===0xb800)red++;
  Object.assign(result,{sequence:frame.sequence,source_sequence:frame.sourceSequence,
    red_pixels:red,unexpected_pixels:240000-red});
  result.matches=red===240000;
  return summary?result:result.matches;
}
