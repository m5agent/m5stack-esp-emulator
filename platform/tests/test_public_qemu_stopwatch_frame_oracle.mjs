// Host-only oracle controls. No QEMU, firmware or synthetic guest execution.
import assert from 'node:assert/strict';
import {runInNewContext} from 'node:vm';
import {stopwatchRedCircleOracle} from './public_qemu_stopwatch_frame_oracle.mjs';

const make=(red=0xf800)=>{
  const pixels=new Uint8Array(466*466*2);
  // Independent scanline construction; the observer uses squared distance.
  for(let y=0;y<466;y++){
    const half=Math.sqrt(233**2-(y-233)**2);
    for(let x=Math.max(0,Math.ceil(233-half));x<=Math.min(465,Math.floor(233+half));x++){
      const at=2*(y*466+x);pixels[at]=red&255;pixels[at+1]=red>>8;
    }
  }
  return {width:466,height:466,pixels};
};
const set=(frame,x,y,color)=>{const at=2*(y*466+x);frame.pixels[at]=color&255;frame.pixels[at+1]=color>>8;return frame;};
const positive=make(),summary=stopwatchRedCircleOracle({frame:positive,summary:true});
assert.equal(summary.matches,true);assert.equal(summary.inside_pixels,170499);assert.equal(summary.outside_pixels,46657);
assert.equal(stopwatchRedCircleOracle({frame:positive}),true);
// Playwright serializes this exact function without its ES module closure.
assert.equal(runInNewContext(`(${stopwatchRedCircleOracle.toString()})()`,{uiflowRuntime:{lastFrame:positive}}),true);
const half=stopwatchRedCircleOracle({frame:make(0x7800),summary:true});
assert.equal(half.matches,false);assert.equal(half.wrong_inside_pixels,170499); // first failure must remain rejected
const rectangular=make();for(let at=0;at<rectangular.pixels.length;at+=2){rectangular.pixels[at]=0;rectangular.pixels[at+1]=0xf8;}
const full=stopwatchRedCircleOracle({frame:rectangular,summary:true});
assert.equal(full.matches,false);assert.equal(full.wrong_outside_pixels,46657); // no corner leakage
const oneInside=stopwatchRedCircleOracle({frame:set(make(),233,233,0x07e0),summary:true});
assert.equal(oneInside.matches,false);assert.equal(oneInside.wrong_inside_pixels,1);
const oneOutside=stopwatchRedCircleOracle({frame:set(make(),0,0,0xf800),summary:true});
assert.equal(oneOutside.matches,false);assert.equal(oneOutside.wrong_outside_pixels,1);
assert.equal(stopwatchRedCircleOracle({frame:set(make(),0,233,0)}),false); // r² boundary belongs inside
assert.equal(stopwatchRedCircleOracle({frame:set(make(),0,232,0xf800)}),false); // r²+1 belongs outside
assert.equal(stopwatchRedCircleOracle({frame:{...positive,width:468,height:468}}),false); // logical size is not physical
assert.equal(stopwatchRedCircleOracle({frame:{...positive,pixels:positive.pixels.subarray(0,-2)}}),false);
assert.equal(stopwatchRedCircleOracle({frame:null}),false);
assert.equal(stopwatchRedCircleOracle({frame:make(0x001f)}),false);
assert.equal(stopwatchRedCircleOracle({frame:make(0)}),false);
console.log('StopWatch exact round-frame oracle: positive and 11 negative controls passed; guest NOT RUN');
