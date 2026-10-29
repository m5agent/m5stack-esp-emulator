// A same-origin iframe admits exactly one parent-owned private MessagePort.
// All guest execution and MEMFS work belongs to one module DedicatedWorker.
let connected=false,engine,heldPort,readyTimer;
let engineWorkersCreated=0,engineOwnerLive=false,engineCloseNotificationReceived=false;
let engineSelfCloseNotifications=0,engineFallbackTerminations=0,enginePortTransferred=false,engineTerminationRequested=false;
// Compatibility field: normal disposal no longer calls owner terminate().
const engineNormalTerminations=0;
Object.defineProperty(globalThis,'m5QemuEngineOwnership',{get:()=>Object.freeze({
  engineWorkersCreated,engineOwnerLive,engineCloseNotificationReceived,
  engineSelfCloseNotifications,engineNormalTerminations,engineFallbackTerminations,enginePortTransferred,
})});
function finalizeOwner() {
  if (engineTerminationRequested || engineCloseNotificationReceived) return;
  engineCloseNotificationReceived=true;engineSelfCloseNotifications++;engineOwnerLive=false;
  // The engine owns its cooperative self.close(). An immediate terminate()
  // here races that close and can leave its browser target behind. These
  // fields record owner disposition and notification, never actual exit.
}
function terminateOwner() {
  if (!engine || engineTerminationRequested) return;
  engineTerminationRequested=true;engineFallbackTerminations++;engineOwnerLive=false;engine.terminate();
}
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
    engine=new Worker(new URL('./public-qemu-engine.js',import.meta.url),{type:'module',name:'m5-qemu-engine'});
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
addEventListener('pagehide',()=>{
  clearTimeout(readyTimer);heldPort?.close();heldPort=null;
  // A normal close notification precedes engine self.close(), not proof of
  // exit. Let that path finish; unannounced teardown still needs a fallback.
  if(!engineCloseNotificationReceived)terminateOwner();
});
