// A same-origin iframe admits exactly one parent-owned private MessagePort.
// All guest execution and MEMFS work belongs to one module DedicatedWorker.
let connected=false,engine,heldPort,readyTimer;
let engineWorkersCreated=0,engineOwnerLive=false,engineCloseNotificationReceived=false;
let engineCloseNotifications=0,engineNormalTerminations=0,engineFallbackTerminations=0;
let enginePortTransferred=false,engineTerminationRequested=false;
Object.defineProperty(globalThis,'m5QemuEngineOwnership',{get:()=>Object.freeze({
  engineWorkersCreated,engineOwnerLive,engineCloseNotificationReceived,
  engineCloseNotifications,engineNormalTerminations,engineFallbackTerminations,enginePortTransferred,
  // Historical runners use this key for the engine's closing message count.
  engineSelfCloseNotifications:engineCloseNotifications,
})});
function finalizeOwner() {
  if (engineTerminationRequested || engineCloseNotificationReceived) return;
  engineCloseNotificationReceived=true;engineCloseNotifications++;engineOwnerLive=false;
  // The engine has disposed its resources and closed the port. Only the
  // iframe owner terminates the Worker, once, on this acknowledged path.
  engineTerminationRequested=true;engineNormalTerminations++;
  const worker=engine;engine=null;worker.terminate();
}
function terminateOwner() {
  if (!engine || engineTerminationRequested) return;
  engineTerminationRequested=true;engineFallbackTerminations++;engineOwnerLive=false;
  const worker=engine;engine=null;worker.terminate();
}
function releaseEngine() {
  connected=true;
  clearTimeout(readyTimer);heldPort?.close();heldPort=null;
  terminateOwner();
}
Object.defineProperty(globalThis,'m5QemuReleaseEngine',{value:releaseEngine});
function failBeforeTransfer(error) {
  if (!heldPort) return;
  heldPort.postMessage({type:'error',value:String(error?.message||error)});
  heldPort.close();heldPort=null;clearTimeout(readyTimer);terminateOwner();
}
addEventListener('message', event => {
  if (connected || event.source!==parent || event.origin!==location.origin ||
      event.data?.type!=='m5-qemu-connect' || event.ports?.length!==1) return;
  connected=true;heldPort=event.ports[0];heldPort.start();
  try {
    // The parent's Worker realm remains active through nested thread shutdown
    // after the per-guest iframe and its private port are removed.
    engine=new parent.Worker(new URL('./public-qemu-engine.js',import.meta.url),{type:'module',name:'m5-qemu-engine'});
    engineWorkersCreated++;engineOwnerLive=true;
    engine.addEventListener('message',({data})=>{
      if (data?.type==='m5-qemu-engine-listening' && heldPort) {
        clearTimeout(readyTimer);
        try {
          engine.postMessage({type:'m5-qemu-engine-connect'},[heldPort]);
          enginePortTransferred=true;heldPort=null;
        } catch(error) { failBeforeTransfer(error); }
      } else if (data?.type==='m5-qemu-engine-closing' && enginePortTransferred) {
        finalizeOwner();
      }
    });
    engine.addEventListener('error',event=>{
      if(heldPort)failBeforeTransfer(event.message||'QEMU engine failed');
      else terminateOwner();
    });
    readyTimer=setTimeout(()=>failBeforeTransfer('QEMU engine initialization timed out'),30000);
  } catch(error) { failBeforeTransfer(error); }
});
addEventListener('pagehide',releaseEngine);
