// Shared display ABI contracts only. Synthetic host buffers do not run a guest.
import assert from 'node:assert/strict';
import {readSharedQemuFrame} from '../web/public-qemu-frame.js';

function fixture(){
  const heap=new Uint8Array(new SharedArrayBuffer(256)),words=new Uint32Array(heap.buffer,32,8);
  words.set([0x4d354642,2,3,2,8,64,7,0]);
  heap.set([1,2,3,4,5,6,0xee,0xff,7,8,9,10,11,12,0xee,0xff],64);
  return {module:{HEAPU8:heap,_m5_wasm_frame_state:()=>32},heap,words,display:{width:3,height:2}};
}
const read=(test,previous=0)=>readSharedQemuFrame(test.module,previous,test.display);
{
  const test=fixture(),frame=read(test);
  assert.equal(frame.width,3);assert.equal(frame.height,2);assert.equal(frame.format,'rgb565le');
  assert.equal(frame.sourceSequence,2);assert.equal(frame.sourceUpdates,7);assert.equal(frame.source,'qemu-display-surface-shared');
  assert.deepEqual([...frame.pixels],[1,2,3,4,5,6,7,8,9,10,11,12],'stride padding must not leak into the image');
  assert.equal(frame.pixels.buffer instanceof SharedArrayBuffer,false,'the iframe owns an independent transferable snapshot');
  test.heap[64]=99;assert.equal(frame.pixels[0],1,'future writer changes cannot mutate an already delivered frame');
  assert.equal(read(test,2),null,'an unchanged source sequence does not create a new consumer frame');
  Atomics.store(test.words,1,4);const newer=read(test,2);assert.equal(newer.pixels[0],99);assert.notEqual(newer.pixels.buffer,frame.pixels.buffer);
}
for(const sequence of [0,1,3,0xffffffff]){const test=fixture();Atomics.store(test.words,1,sequence);assert.equal(read(test),null);}
{
  const test=fixture();Atomics.store(test.words,0,0);assert.equal(read(test),null,'uninitialized metadata cannot publish pixels');
}
for(const change of [
  test=>delete test.module._m5_wasm_frame_state,
  test=>test.module.HEAPU8=new Uint8Array(256),
  test=>test.module._m5_wasm_frame_state=()=>33,
  test=>test.module._m5_wasm_frame_state=()=>252,
]){const test=fixture();change(test);assert.throws(()=>read(test),/ABI|metadata/);}
for(const [index,value] of [[2,0],[2,1025],[3,0],[3,1025],[4,5],[4,2049],[5,250]]){
  const test=fixture();test.words[index]=value;assert.throws(()=>read(test),/bounds/);
}
{
  const test=fixture();test.display={width:4,height:2};assert.throws(()=>read(test),/selected board/);
}
for(const sequence of [3,4]){
  const test=fixture(),subarray=test.heap.subarray;
  test.heap.subarray=function(...args){Atomics.store(test.words,1,sequence);return subarray.apply(this,args);};
  assert.equal(read(test),null,'a writer beginning or finishing while pixels are copied must discard the snapshot');
}
// Interleave a writer immediately after the initial even sequence load, before
// bounds validation. Invalid in-flight metadata is a retry, not a fatal ABI gap.
{
  const test=fixture(),load=Atomics.load;let changed=false;
  Atomics.load=function(array,index){
    const value=load(array,index);
    if(!changed&&array.byteOffset===32&&index===1){changed=true;Atomics.store(test.words,1,3);test.words[4]=0;}
    return value;
  };
  try{assert.equal(read(test),null,'a sequence race during metadata reads must retry instead of stopping the runtime');}
  finally{Atomics.load=load;}
}
console.log('public QEMU real shared-reader ABI, stride/copy identity, dirty sequence and writer-race contracts passed; no guest executed');
