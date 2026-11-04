// Host-only controls of the frame observer; no browser or guest execution.
import assert from 'node:assert/strict';
import {runInNewContext} from 'node:vm';
import {papercolorRedFrameOracle} from './public_qemu_papercolor_frame_oracle.mjs';
const make=(color=0xb800)=>{
  // Independent 16-bit construction, rather than the oracle's byte scan.
  const colors=new Uint16Array(240000);colors.fill(color);
  return {width:400,height:600,format:'rgb565le',sequence:5,sourceSequence:12,
    pixels:new Uint8Array(colors.buffer)};
};
const bounds={afterSequence:4,afterSourceSequence:10};
const positive=make(),summary=papercolorRedFrameOracle({frame:positive,...bounds,summary:true});
assert.equal(summary.matches,true);assert.equal(summary.red_pixels,240000);assert.equal(summary.unexpected_pixels,0);
assert.equal(runInNewContext(`(${papercolorRedFrameOracle.toString()})(${JSON.stringify(bounds)})`,
  {uiflowRuntime:{lastFrame:positive}}),true,'serialized browser observer has no module closure');
const negative=[
  make(0xf800),make(0xffff),make(0),make(0x001f),make(0x00b8),
  {...make(),width:600,height:400}, {...make(),height:599},
  {...make(),format:'rgb888'}, {...make(),pixels:positive.pixels.subarray(0,-2)},
  {...make(),sequence:4}, {...make(),sourceSequence:10},
  {...make(),sequence:NaN}, {...make(),sourceSequence:undefined}, null,
];
const oneWrong=make();oneWrong.pixels[0]=1;negative.push(oneWrong);
for(const frame of negative)assert.equal(papercolorRedFrameOracle({frame,...bounds}),false);
const one=papercolorRedFrameOracle({frame:oneWrong,...bounds,summary:true});
assert.equal(one.unexpected_pixels,1);assert.equal(one.red_pixels,239999);
assert.equal(papercolorRedFrameOracle({frame:positive,...bounds,afterSequence:-1}),false);
console.log('PaperColor exact Spectra6 red/fresh-frame oracle: positive and 16 negative controls passed; guest NOT RUN');
