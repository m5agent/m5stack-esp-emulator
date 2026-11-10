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
  let engineWorkersCreated=0,engineCloseNotifications=0,engineFallbackTerminations=0,enginePortTransferred=false;
  const finalizeMode=new URL(url).searchParams.get('m5-worker-finalization');
  let engineNormalTerminations=0,finalizationToken,finalization;

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
    if(worker){engineFallbackTerminations++;worker.terminate();}
  }
  function failBeforeTransfer(error) {
    if(!heldPort)return;
    try{heldPort.postMessage({type:'error',value:String(error?.message||error)});}
    finally{release();}
  }
  function receive({currentTarget,data}) {
    if(!engine||currentTarget!==engine)return;
    if(data?.type==='m5-qemu-engine-listening'&&heldPort){
      clearTimeout(readyTimer);
      try{
        engine.postMessage({type:'m5-qemu-engine-connect'},[heldPort]);
        enginePortTransferred=true;heldPort=null;
      }catch(error){failBeforeTransfer(error);}
    }else if(!finalizeMode&&data?.type==='m5-qemu-engine-closing'&&enginePortTransferred){
      engineCloseNotifications++;
      detachWorker();
    }else if(finalizeMode&&enginePortTransferred&&data?.type==='m5-qemu-engine-drained'
      &&data.mode===finalizeMode&&!finalizationToken){
      finalizationToken=crypto.randomUUID();
      finalization={mode:finalizeMode,port_drained_worker_epoch_ms:data.worker_epoch_ms,
        request_page_epoch_ms:performance.timeOrigin+performance.now()};
      try{
        engine.postMessage({type:'m5-qemu-engine-finalize',token:finalizationToken});
      }catch(error){
        finalization.request_error=String(error?.message||error);
        release();onError();
      }
    }else if(finalizeMode&&finalizationToken&&data?.type==='m5-qemu-engine-finalized'
      &&data.token===finalizationToken){
      engineCloseNotifications++;
      Object.assign(finalization,{finalized_worker_epoch_ms:data.worker_epoch_ms,
        acknowledgement_page_epoch_ms:performance.timeOrigin+performance.now()});
      const worker=detachWorker();
      if(finalizeMode==='finalize-owner'){
        engineNormalTerminations++;
        worker.terminate();
      }
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
    engineSelfCloseNotifications:finalizeMode==='finalize-owner'?0:engineCloseNotifications,
    ...(finalizeMode?{engineFinalization:finalization||null}:{})});

  heldPort.start();
  globalThis.addEventListener('pagehide',release);
  try{
    engine=new Worker(url,{type:'module',name:'m5-qemu-engine'});
    engineWorkersCreated++;
    engine.addEventListener('message',receive);
    engine.addEventListener('error',fail);
    readyTimer=setTimeout(()=>failBeforeTransfer('QEMU engine initialization timed out'),30000);
  }catch(error){failBeforeTransfer(error);}
  return {observe,release};
}
