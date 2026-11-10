// This same-origin iframe admits and returns exactly one parent-owned port.
// The top page binds its Worker only after that origin/source handshake.
let connected=false;
addEventListener('message',event=>{
  if(connected||event.source!==parent||event.origin!==location.origin
    ||event.data?.type!=='m5-qemu-connect'||typeof event.data.sessionId!=='string'
    ||!event.data.sessionId||event.ports?.length!==1)return;
  connected=true;
  const [port]=event.ports;
  try{parent.postMessage({type:'m5-qemu-admitted',sessionId:event.data.sessionId},location.origin,[port]);}
  catch{port.close();}
});
