// The iframe admits one private port. The workbench owns the Worker and every
// callback for its lifetime in the top document.
export function admitQemuEnginePort(iframe, origin, sessionId, port, signal) {
  return new Promise((resolve,reject)=>{
    const finish=(error,admittedPort)=>{
      clearTimeout(timer);
      globalThis.removeEventListener('message',receive);
      signal.removeEventListener('abort',abort);
      if(error){port.close();reject(error);}
      else resolve(admittedPort);
    };
    const abort=()=>finish(new DOMException('启动已取消','AbortError'));
    const receive=({source,origin:sender,data,ports})=>{
      if(!source||signal.aborted||source!==iframe.contentWindow||sender!==origin||data?.type!=='m5-qemu-admitted'
        ||data.sessionId!==sessionId||ports?.length!==1)return;
      finish(null,ports[0]);
    };
    const timer=setTimeout(()=>finish(new Error('浏览器设备容器连接超时。')),15000);
    if(signal.aborted){abort();return;}
    signal.addEventListener('abort',abort,{once:true});
    globalThis.addEventListener('message',receive);
    try{iframe.contentWindow.postMessage({type:'m5-qemu-connect',sessionId},origin,[port]);}
    catch(error){finish(error);}
  });
}

export function createQemuEngineOwner(url, port, onError) {
  let engine,readyTimer,heldPort=port;
  let engineWorkersCreated=0,engineCloseNotifications=0,engineNormalTerminations=0,engineFallbackTerminations=0;
  let enginePortTransferred=false,portDrained=false,disposalAcknowledged=false,finalizationToken;
  const pthreads=new Map();
  let pthreadSource,pthreadsCreated=0,pthreadTerminations=0,pthreadFallbackTerminations=0;

  function stopPthread(id,fallback=false) {
    const item=pthreads.get(id);
    if(!item)return;
    pthreads.delete(id);
    item.relay.onmessage=null;item.relay.onmessageerror=null;item.relay.close();
    item.worker.removeEventListener('message',item.fromThread);
    item.worker.removeEventListener('error',item.fromError);
    item.worker.removeEventListener('messageerror',item.fromMessageError);
    item.worker.terminate();
    if(fallback)pthreadFallbackTerminations++;else pthreadTerminations++;
  }
  function releasePthreads() {
    for(const id of pthreads.keys())stopPthread(id,true);
  }
  function spawnPthread(data,relay) {
    const reportError=(detail)=>relay.postMessage({type:'error',detail});
    let worker;
    try{worker=new Worker(pthreadSource,{type:'module',name:'m5-qemu-pthread'});}
    catch{rejectPthreadControl([relay]);return;}
    const fromThread=event=>{
      const ports=Array.from(event.ports||[]);
      const declared=Array.isArray(event.data?.transferList)?event.data.transferList:[];
      const transfer=[...new Set([...ports,...declared])];
      try{relay.postMessage({type:'message',payload:event.data,ports},transfer);}
      catch(error){reportError({message:String(error?.message||error)});}
    };
    const fromError=event=>{
      event.preventDefault();
      reportError({message:event.message,filename:event.filename,lineno:event.lineno,colno:event.colno});
    };
    const fromMessageError=()=>reportError({message:'Could not deserialize the QEMU pthread message'});
    pthreads.set(data.id,{worker,relay,fromThread,fromError,fromMessageError});
    pthreadsCreated++;
    worker.addEventListener('message',fromThread);
    worker.addEventListener('error',fromError);
    worker.addEventListener('messageerror',fromMessageError);
    relay.onmessage=({data})=>{
      if(data?.type!=='message')return;
      try{worker.postMessage(data.payload,data.transfer);}
      catch(error){reportError({message:String(error?.message||error)});}
    };
    relay.onmessageerror=fromMessageError;
    relay.start();
  }
  function rejectPthreadControl(ports) {
    for(const port of ports||[])port.close();
    release();onError();
  }

  function detachWorker() {
    const worker=engine;engine=null;
    worker?.removeEventListener('message',receive);
    worker?.removeEventListener('error',fail);
    globalThis.removeEventListener('pagehide',release);
    return worker;
  }
  function release() {
    clearTimeout(readyTimer);heldPort?.close();heldPort=null;
    const worker=detachWorker();
    releasePthreads();
    if(worker){engineFallbackTerminations++;worker.terminate();}
  }
  function failBeforeTransfer(error) {
    if(!heldPort)return;
    try{heldPort.postMessage({type:'error',value:String(error?.message||error)});}
    finally{release();}
  }
  function requestFinalization() {
    if(!engine||!portDrained||!disposalAcknowledged||finalizationToken||pthreads.size
      ||pthreadTerminations!==pthreadsCreated||pthreadFallbackTerminations)return;
    finalizationToken=crypto.randomUUID();
    try{engine.postMessage({type:'m5-qemu-engine-finalize',token:finalizationToken});}
    catch{release();onError();}
  }
  function acknowledgeDisposal(disposal) {
    if(!engine||!enginePortTransferred||disposal?.enginePlacement!=='dedicated-worker-v1'
      ||disposal.engineWorkersAtAcknowledgement!==1||disposal.workersRemaining!==0||disposal.workersTerminatedByDispose!==0
      ||disposal.ownerTerminatesAfterAcknowledgement!==true||disposal.engineSelfClosesAfterAcknowledgement!==false)return;
    disposalAcknowledged=true;
    requestFinalization();
  }
  function receive({currentTarget,data,ports}) {
    if(!engine||currentTarget!==engine)return;
    if(data?.type==='m5-qemu-engine-listening'&&heldPort){
      clearTimeout(readyTimer);
      try{
        engine.postMessage({type:'m5-qemu-engine-connect'},[heldPort]);
        enginePortTransferred=true;heldPort=null;
      }catch(error){failBeforeTransfer(error);}
    }else if(data?.type==='m5-qemu-pthread-source'&&enginePortTransferred){
      try{
        const source=new URL(data.url);
        if(pthreadSource||portDrained||ports?.length||source.protocol!=='blob:'||source.origin!==new URL(url).origin)
          throw new Error('Invalid verified QEMU pthread source');
        pthreadSource=source.href;
      }catch{rejectPthreadControl(ports);}
    }else if(data?.type==='m5-qemu-pthread-spawn'&&enginePortTransferred){
      if(!pthreadSource||portDrained||data.url!==pthreadSource||data.id!==pthreadsCreated+1||ports?.length!==1){
        rejectPthreadControl(ports);return;
      }
      spawnPthread(data,ports[0]);
    }else if(data?.type==='m5-qemu-pthread-terminate'&&enginePortTransferred){
      if(!pthreads.has(data.id)||ports?.length){rejectPthreadControl(ports);return;}
      stopPthread(data.id);
    }else if(data?.type==='m5-qemu-engine-drained'&&enginePortTransferred){
      portDrained=true;
      requestFinalization();
    }else if(data?.type==='m5-qemu-engine-finalized'&&finalizationToken&&data.token===finalizationToken){
      const worker=detachWorker();
      worker.terminate();
      engineCloseNotifications++;engineNormalTerminations++;
    }else if(data?.type==='m5-qemu-engine-closing'&&enginePortTransferred&&!portDrained&&!disposalAcknowledged){
      engineCloseNotifications++;
      releasePthreads();
      detachWorker();
    }
  }
  function fail({currentTarget,message}) {
    if(!engine||currentTarget!==engine)return;
    if(heldPort){failBeforeTransfer(message||'QEMU engine failed');return;}
    release();
    onError();
  }
  const observe=()=>({engineWorkersCreated,engineOwnerLive:!!engine,engineCloseNotificationReceived:engineCloseNotifications>0,
    engineCloseNotifications,engineNormalTerminations,engineFallbackTerminations,enginePortTransferred,
    engineFinalizationAcknowledged:engineNormalTerminations===1,
    engineSelfCloseNotifications:engineCloseNotifications-engineNormalTerminations,
    pthreadBroker:{created:pthreadsCreated,live:pthreads.size,terminations:pthreadTerminations,fallbackTerminations:pthreadFallbackTerminations}});

  heldPort.start();
  globalThis.addEventListener('pagehide',release);
  try{
    engine=new Worker(url,{type:'module',name:'m5-qemu-engine'});
    engineWorkersCreated++;
    engine.addEventListener('message',receive);
    engine.addEventListener('error',fail);
    readyTimer=setTimeout(()=>failBeforeTransfer('QEMU engine initialization timed out'),30000);
  }catch(error){failBeforeTransfer(error);}
  return {observe,release,acknowledgeDisposal};
}
