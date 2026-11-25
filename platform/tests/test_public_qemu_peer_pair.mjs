import assert from 'node:assert/strict';
import {setTimeout as wait} from 'node:timers/promises';
import {openQemuPeerPair} from '../web/public-qemu-peer-pair.js';
import {validCc1101PeerFrame} from '../web/public-qemu-profiles.js';

const members=new Map(), messages=[];
function openChannel(name){
  const group=members.get(name)||new Set();
  members.set(name,group);
  const channel={
    postMessage(data){
      messages.push({name,data});
      for(const target of group)
        if(target!==channel)queueMicrotask(()=>{if(group.has(target))target.onmessage?.({data:structuredClone(data)});});
    },
    close(){group.delete(channel);if(!group.size)members.delete(name);},
  };
  group.add(channel);
  return channel;
}
let n=0;
const token=()=> (++n).toString(16).padStart(32,'0');
const code=token();
const txState={epoch:0,sequence:10,frameHex:'026162'};
const rxState={epoch:0,armed:false};
const txEvents=[],rxEvents=[],thirdEvents=[],writes=[];
const defaults={protocol:'cc1101',code,scope:'/test/',validateFrame:validCc1101PeerFrame,
  openChannel,createToken:token,pollMs:5,ackMs:500};
const pair=(role,options={})=>openQemuPeerPair({
  ...defaults,role,readState:async()=>structuredClone(role==='tx'?txState:rxState),...options,
});
async function until(predicate,message){
  for(let i=0;i<100;i++){
    if(predicate())return;
    await wait(5);
  }
  throw new Error(message);
}
const tx=pair('tx',{onStatus:status=>txEvents.push(status)});
let finish;
const rx=pair('rx',{onStatus:status=>rxEvents.push(status),receiveFrame:frame=>{
  writes.push(frame);
  return new Promise(resolve=>{finish=resolve;});
}});
const other=pair('rx',{protocol:'sx1262'});
const invalid=pair('tx',{scope:'/other/'});
let third;
try{
  assert.throws(()=>pair('tx',{code:'wrong'}),/32/);
  await until(()=>txEvents.some(event=>event.state==='paired'),'same-scope pair');
  third=pair('tx',{onStatus:status=>thirdEvents.push(status)});
  assert.equal(messages.filter(({data})=>data.type==='frame').length,0);
  txState.sequence++;
  await wait(15);
  assert.deepEqual(writes,[],'no frame enters an unarmed chip');
  rxState.armed=true;
  await until(()=>messages.some(({data})=>data.type==='ready'),'receiver announced actual arm state');
  await wait(15);
  assert.deepEqual(writes,[],'receiver joining does not replay old completed TX');
  txState.epoch++;
  txState.sequence=1;
  txState.frameHex='026364';
  await until(()=>writes.length===1,'deliver exact FIFO once');
  assert.deepEqual(writes,['026364']);
  assert.ok(thirdEvents.every(event=>event.state==='waiting'),'a third tab cannot join the active pair');
  const delivery=messages.find(({data})=>data.type==='frame');
  const replay=openChannel(delivery.name);
  replay.postMessage({...delivery.data,frameHex:'036364'});
  replay.postMessage(delivery.data);
  txState.sequence+=2;
  await wait(25);
  assert.deepEqual(writes,['026364'],'duplicate and malformed frames cannot grow the writer queue');
  assert.equal(messages.filter(({data})=>data.type==='frame').length,3,'only one sender frame and two injected test messages');
  finish({accepted:true});
  await until(()=>txEvents.at(-1)?.accepted===1,'receiver acknowledgement propagated');
  assert.equal(rxEvents.at(-1).accepted,1);
  replay.postMessage(delivery.data);
  await wait(15);
  assert.equal(writes.length,1,'consumed readiness ticket cannot be reused');
  replay.close();
  third.close();
  tx.close();
  await until(()=>rxEvents.at(-1)?.state==='disconnected','closing sender disconnects receiver');
  assert.deepEqual([...members.keys()].sort(),[`m5-qemu-peer:cc1101:/other/:${code}`,
    `m5-qemu-peer:sx1262:/test/:${code}`]);
} finally {
  tx.close();rx.close();other.close();invalid.close();third?.close();
}
assert.equal(members.size,0);

const epochMessages=[];
const previousReady=messages.filter(({data})=>data.type==='ready').length;
let staleWrites=0;
const epochTx=pair('tx');
const epochRx=pair('rx',{
  receiveFrame:async()=>{staleWrites++;return {accepted:true};},
  onStatus:status=>epochMessages.push(status),
});
try{
  await until(()=>epochMessages.at(-1)?.state==='paired','new generation pairs separately');
  await until(()=>messages.filter(({data})=>data.type==='ready').length>previousReady,'receiver arm cycle');
  rxState.armed=false;
  rxState.epoch++;
  txState.sequence++;
  await wait(35);
  assert.equal(staleWrites,0,'reset receiver rejects a stale readiness ticket');
  assert.ok(!epochMessages.some(event=>event.accepted>0));
} finally {
  epochTx.close();epochRx.close();
}
assert.equal(members.size,0);
console.log('public QEMU virtual peer pair contract passed');
