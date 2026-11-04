// MicroPython's UART raw-paste protocol. Code executes in the guest VM.
const encoder = new TextEncoder();
const prompt = encoder.encode('raw REPL; CTRL-B to exit\r\n>');
const abort = message => new DOMException(message, 'AbortError');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export class PublicMicroPythonRunner {
  constructor(runtime) { this.runtime=runtime; this.busy=false; }
  async interrupt() {
    if(!this.busy)return;
    const current=this.current;
    if(!current||this.runtime.generation!==current.generation||this.runtime.sessionId!==current.sessionId
      ||this.runtime.consoleEpoch!==current.consoleEpoch)throw abort('设备会话已改变。');
    this.runtime.requireUartOwner(current.owner);
    if(current.phase!=='running')throw new Error('代码正在传输，请稍后中断或停止设备。');
    if(this.runtime.status==='paused')throw new Error('设备已暂停，请先继续后再中断。');
    if(current.interruptPromise)return current.interruptPromise;
    this.interrupted=true;current.interruptDeadline=Date.now()+5000;
    // One exception must leave the guest's finally/deinit code free to run.
    // Latch before transport so repeat requests cannot inject another one.
    current.interruptPromise=Promise.resolve().then(()=>this.runtime.writeUart(new Uint8Array([3]),current.owner));
    await current.interruptPromise;
  }
  async run(source, {onOutput=()=>{},onPhase=()=>{},signal,timeoutMs=30000}={}) {
    if(this.busy)throw new Error('代码仍在运行，请先中断。');
    if(typeof source!=='string'||!source.trim())throw new Error('请输入 MicroPython 代码。');
    if(/[\x00-\x08\x0b\x0e-\x1f\x7f]/.test(source))throw new Error('源码含有原始串口控制字符，请在字符串中使用反斜杠转义。');
    const data=encoder.encode(source);
    if(data.length>65536)throw new Error('代码超过 64 KiB，请缩短后重试。');
    if(!Number.isFinite(timeoutMs)||timeoutMs<100||timeoutMs>120000)throw new Error('无效的串口超时。');
    const runtime=this.runtime, generation=runtime.generation, session=runtime.sessionId, consoleEpoch=runtime.consoleEpoch;
    const owner=runtime.acquireUart();
    this.busy=true;this.interrupted=false;
    const current=this.current={generation,sessionId:session,consoleEpoch,owner,phase:'connecting',interruptDeadline:Infinity};
    const phase=value=>{current.phase=value;onPhase(value);};
    let buffer=[],offset=0,deadline=Date.now()+timeoutMs,lastTick=Date.now();
    let unsubscribe=()=>{};
    const receive=bytes=>{
      if(runtime.generation!==generation||runtime.sessionId!==session||runtime.consoleEpoch!==consoleEpoch)return;
      // Keep unread output bounded even if a guest floods its UART.
      if(buffer.length-offset+bytes.length>131072){this.overflow=true;return;}
      if(offset>65536){buffer=buffer.slice(offset);offset=0;}
      buffer.push(...bytes);
    };
    this.overflow=false;
    const active=()=>{
      if(signal?.aborted||runtime.generation!==generation||runtime.sessionId!==session||runtime.consoleEpoch!==consoleEpoch||runtime.stopping
        ||!['booting','running','paused'].includes(runtime.status))throw abort('设备会话已改变，代码执行已结束。');
      runtime.requireUartOwner(owner);
      const now=Date.now();
      if(runtime.status==='paused'){deadline+=now-lastTick;current.interruptDeadline+=now-lastTick;}
      lastTick=now;
      if(Date.now()>current.interruptDeadline)throw new Error('设备未响应中断，请停止或重新启动设备。');
      if(this.overflow)throw new Error('串口输出超过缓冲区上限，请减少输出频率。');
      if(Date.now()>deadline)throw new Error('等待 MicroPython 串口响应超时。可中断后重试或重启设备。');
    };
    const read=async count=>{
      while(buffer.length-offset<count){active();await delay(10);}
      active();const bytes=Uint8Array.from(buffer.slice(offset,offset+count));offset+=count;return bytes;
    };
    const write=async bytes=>{
      active();while(runtime.status==='paused'){await delay(10);active();}
      await runtime.writeUart(Uint8Array.from(bytes),owner);
    };
    const marker=async bytes=>{
      for(;;){
        active();
        for(let i=offset;i+bytes.length<=buffer.length;i++){
          if(bytes.every((byte,j)=>buffer[i+j]===byte)){offset=i+bytes.length;return;}
        }
        await delay(10);
      }
    };
    try {
      unsubscribe=runtime.subscribeUart(receive);
      phase('connecting');
      await write([13,3,3]);await delay(100);await write([13,1]);await marker(prompt);
      phase('uploading');
      await write([5,65,1]);const response=await read(2);
      let transfer;
      if(response[0]===82&&response[1]===1){
        const size=await read(2),window=size[0]+size[1]*256;
        if(!window)throw new Error('MicroPython 返回了无效的传输窗口。');
        let credit=window,sent=0;
        while(sent<data.length){
          while(credit===0||buffer.length>offset){
            const byte=(await read(1))[0];
            if(byte===1)credit+=window;
            else if(byte===4){await write([4]);throw new Error('MicroPython 提前结束了代码传输。');}
            else throw new Error('MicroPython 传输控制字节无效。');
          }
          const count=Math.min(credit,128,data.length-sent);
          await write(data.subarray(sent,sent+count));sent+=count;credit-=count;
        }
        await write([4]);
        let byte=(await read(1))[0];while(byte===1)byte=(await read(1))[0];
        if(byte!==4)throw new Error('MicroPython 未确认代码传输。');
        transfer='raw-paste';
      }else{
        if(response[0]===114&&response[1]===97)await marker(prompt.subarray(2));
        else if(response[0]!==82||response[1]!==0)throw new Error('此固件未提供兼容的 MicroPython REPL。');
        for(let sent=0;sent<data.length;sent+=128){await write(data.subarray(sent,sent+128));await delay(10);}
        await write([4]);const ok=await read(2);
        if(ok[0]!==79||ok[1]!==75)throw new Error('MicroPython 未确认代码传输。');
        transfer='raw-repl';
      }
      phase('running');
      // UIFlow programs commonly run forever. Only transfer is timed; the
      // user can interrupt execution, stop the VM, or switch the device.
      deadline=Infinity;
      const outputs=[];
      for(const channel of ['stdout','stderr']){
        const decoder=new TextDecoder();let output='',done=false;
        while(!done){
          await read(0);active();
          if(offset===buffer.length){await delay(10);continue;}
          let end=buffer.indexOf(4,offset);done=end!==-1;if(!done)end=buffer.length;
          const text=decoder.decode(Uint8Array.from(buffer.slice(offset,end)),{stream:!done});
          offset=end+(done?1:0);output=(output+text).slice(-65536);
          if(text)onOutput(text,channel);
        }
        outputs.push(output);
        if(channel==='stdout')deadline=Date.now()+timeoutMs;
      }
      // Protocol termination still has a finite budget if guest output ends
      // but the prompt is lost. No implicit Ctrl-D/soft reset is sent.
      deadline=Date.now()+timeoutMs;
      if((await read(1))[0]!==62)throw new Error('MicroPython 未返回原始 REPL。');
      await write([2]);
      const result={stdout:outputs[0],stderr:outputs[1],interrupted:this.interrupted,transfer,sessionId:session,consoleEpoch};
      phase(this.interrupted?'interrupted':outputs[1]?'error':'complete');return result;
    }finally{unsubscribe();runtime.releaseUart(owner);this.busy=false;this.current=null;}
  }
}
