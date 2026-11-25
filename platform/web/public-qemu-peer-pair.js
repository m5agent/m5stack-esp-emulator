const token=value=>typeof value==='string'&&/^[0-9a-f]{32}$/.test(value);
const counter=value=>Number.isSafeInteger(value)&&value>=0;
const roleNames=new Set(['tx','rx']);
export const newQemuPeerCode=()=>crypto.randomUUID().replaceAll('-','');

/** One same-origin TX/RX pair. Exchange only completed and validated model FIFO snapshots. */
export function openQemuPeerPair({
  protocol,role,code,scope,readState,validateFrame,receiveFrame,onStatus=()=>{},canUse=()=>true,
  openChannel=name=>new BroadcastChannel(name),createToken=newQemuPeerCode,
  pollMs=250,ackMs=6000,
}){
  code=typeof code==='string'?code.trim().toLowerCase():'';
  if(!roleNames.has(role)||!token(code)||typeof scope!=='string'||!scope.startsWith('/')
    ||typeof protocol!=='string'||!/^[a-z0-9-]{1,24}$/.test(protocol))
    throw new Error('请输入配对标签页中生成的 32 位配对码。');
  const opposite=role==='rx'?'tx':'rx', id=createToken();
  const channel=openChannel(`m5-qemu-peer:${protocol}:${scope}:${code}`);
  let peer,ready,pending,queued,timer,closed=false,confirmed=false,reading=false,receiving=false,seenTx,lastReady=0,accepted=0;

  function validFrame(frame){
    return typeof frame==='string'&&/^(?:[0-9a-f]{2}){1,256}$/.test(frame)&&validateFrame(frame);
  }
  async function snapshot(){
    const value=await readState();
    if(!value||!counter(value.epoch)||!(role==='rx'?typeof value.armed==='boolean':
      counter(value.sequence)&&typeof value.frameHex==='string'))
      throw new Error('QEMU peer state has unexpected fields');
    return value;
  }
  function post(type,fields={}){
    channel.postMessage({type,role,from:id,...fields});
  }
  function close({notify=true,reason='disconnected'}={}){
    if(closed)return;
    closed=true;
    clearInterval(timer);
    clearTimeout(pending?.timeout);
    if(notify&&peer)post('bye',{to:peer});
    channel.close();
    onStatus({state:reason,accepted});
  }
  function bind(from){
    if(peer)return peer===from;
    peer=from;
    post('present',{to:peer});
    return true;
  }
  function reply(ticket,sequence,ok){
    if(ok)accepted++;
    post('ack',{to:peer,ticket,sequence,ok});
    onStatus({state:ok?'paired':'receiver-rejected',accepted});
  }
  async function accept({frameHex,ticket,sequence}){
    if(receiving||!ready||ready.ticket!==ticket||!counter(sequence)
      ||!validFrame(frameHex)||!canUse())return;
    if(reading){queued??={frameHex,ticket,sequence};return;}
    const epoch=ready.epoch;
    ready=null;
    receiving=true;
    try{
      const state=await snapshot();
      if(closed)return;
      if(!canUse()||!state.armed||state.epoch!==epoch){
        reply(ticket,sequence,false);
        return;
      }
      const result=await receiveFrame(frameHex);
      if(!closed)reply(ticket,sequence,result?.accepted===true);
    }catch{
      if(!closed)reply(ticket,sequence,false);
    }finally{
      receiving=false;
    }
  }
  channel.onmessage=({data:m})=>{
    if(closed||!m||m.role!==opposite||!token(m.from)||m.from===id)return;
    if(m.type==='hello'){bind(m.from);return;}
    if(m.to!==id)return;
    if(m.type==='present'){
      if(!confirmed&&bind(m.from)){
        confirmed=true;
        onStatus({state:'paired',accepted});
      }
      return;
    }
    if(!confirmed||m.from!==peer)return;
    if(m.type==='bye'){close({notify:false});return;}
    if(role==='tx'){
      if(m.type==='ready'&&!pending&&token(m.ticket)&&counter(m.number)&&m.number>lastReady){
        lastReady=m.number;
        ready={ticket:m.ticket};
      }
      if(m.type==='ack'&&pending&&m.ticket===pending.ticket&&m.sequence===pending.sequence&&typeof m.ok==='boolean'){
        clearTimeout(pending.timeout);
        pending=null;
        if(m.ok)accepted++;
        onStatus({state:m.ok?'paired':'receiver-rejected',accepted});
      }
    }else if(m.type==='frame'){
      void accept(m);
    }
  };
  async function tick(){
    if(closed||receiving||reading||!canUse())return;
    if(!confirmed){post('hello');return;}
    reading=true;
    try{
      const state=await snapshot();
      if(closed||!canUse())return;
      if(role==='rx'){
        if(!state.armed){ready=null;return;}
        if(!ready||ready.epoch!==state.epoch)
          ready={ticket:createToken(),epoch:state.epoch,number:++lastReady};
        post('ready',{to:peer,ticket:ready.ticket,number:ready.number});
        return;
      }
      const previous=seenTx;
      seenTx={epoch:state.epoch,sequence:state.sequence};
      if(!previous||pending||!ready||!validFrame(state.frameHex))return;
      // A chip reset may occur between polls while the official program starts.
      const previousSequence=previous.epoch===state.epoch?previous.sequence:0;
      if(state.epoch<previous.epoch||state.sequence<=previousSequence)return;
      const {ticket}=ready, sequence=state.sequence;
      ready=null;
      pending={ticket,sequence,timeout:setTimeout(()=>close({reason:'timeout'}),ackMs)};
      post('frame',{to:peer,ticket,sequence,frameHex:state.frameHex});
    }catch{
      if(!closed)close({reason:'unavailable'});
    }finally{
      reading=false;
      const next=queued;
      queued=null;
      if(next&&!closed)void accept(next);
    }
  }
  onStatus({state:'waiting',accepted});
  timer=setInterval(()=>void tick(),pollMs);
  void tick();
  return {close};
}
