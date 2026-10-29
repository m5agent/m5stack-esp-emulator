// Test-only browser observers. They time the existing controller and never
// replace guest/controller values, alter frame cadence, or inject firmware.
export function distribution(values) {
  const sorted=values.filter(Number.isFinite).sort((a,b)=>a-b);
  if(!sorted.length)return {samples:0,min:null,p50:null,p90:null,p95:null,max:null,mean:null};
  const percentile=p=>{const at=(sorted.length-1)*p,low=Math.floor(at),high=Math.ceil(at);return sorted[low]+(sorted[high]-sorted[low])*(at-low);};
  return {samples:sorted.length,min:sorted[0],p50:percentile(.5),p90:percentile(.9),p95:percentile(.95),max:sorted.at(-1),mean:sorted.reduce((sum,value)=>sum+value,0)/sorted.length};
}

export function summarizePerformance(probe,resources) {
  const idle=probe.phases.find(row=>row.name==='steady'),
    frames=probe.frames.filter(row=>row.phase==='steady'&&row.at_ms>=idle.start_ms&&row.at_ms<=idle.end_ms),
    frameRequests=probe.requests.filter(row=>row.phase==='steady'&&row.op==='frame'&&row.ok),
    firstReady=probe.guest_events.find(row=>row.event.kind==='ready'),
    firstFrame=probe.frames.find(row=>row.varied),
    start=probe.start_click_ms;
  const latencies=probe.trials.map(trial=>{
    const click=probe.guest_events.find(row=>row.event.kind==='touch_clicked'&&row.event.clicks===trial.clicks),
      visible=probe.frames.find(row=>click&&row.at_ms>=click.at_ms&&row.roi_digest!==trial.before_roi&&row.roi_digest),
      up=probe.pointer_events.find(row=>row.trial===trial.id&&row.type==='pointerup'),
      down=probe.pointer_events.find(row=>row.trial===trial.id&&row.type==='pointerdown');
    return {...trial,down_ms:down?.at_ms??null,up_ms:up?.at_ms??null,callback_ms:click?.at_ms??null,
      visible_commit_ms:visible?.committed_ms??null,paint_opportunity_ms:visible?.paint_opportunity_ms??null,
      frame_sequence:visible?.sequence??null,after_roi:visible?.roi_digest??null,
      down_to_callback_ms:click&&down?click.at_ms-down.at_ms:null,
      up_to_callback_ms:click&&up?click.at_ms-up.at_ms:null,
      down_to_visible_commit_ms:visible&&down?visible.committed_ms-down.at_ms:null,
      up_to_visible_commit_ms:visible&&up?visible.committed_ms-up.at_ms:null,
      callback_to_visible_commit_ms:visible&&click?visible.committed_ms-click.at_ms:null,
      up_to_paint_opportunity_ms:visible?.paint_opportunity_ms&&up?visible.paint_opportunity_ms-up.at_ms:null};
  });
  const resourceRows=resources.filter(row=>row.phase==='steady');
  const framePhases=Object.fromEntries(['steady','input','paused','stopped'].map(name=>{
    const span=probe.phases.find(row=>row.name===name),duration=span?(span.end_ms-span.start_ms)/1000:0;
    const rows=probe.frames.filter(row=>row.phase===name),requests=probe.requests.filter(row=>row.phase===name&&row.op==='frame'&&row.ok);
    let previous=probe.frames.filter(row=>row.at_ms<(span?.start_ms??0)&&row.sha256).at(-1)?.sha256,changed=0;
    for(const row of rows){if(row.sha256&&row.sha256!==previous){changed++;previous=row.sha256;}}
    return [name,{duration_seconds:duration,requests:requests.length,requests_per_second:duration?requests.length/duration:0,
      delivered_frames:rows.length,delivered_frames_per_second:duration?rows.length/duration:0,
      pixel_change_frames:changed,pixel_change_frames_per_second:duration?changed/duration:0,
      pixel_payload_bytes:rows.reduce((sum,row)=>sum+(row.pixels_bytes??row.width*row.height*2),0)}];
  }));
  const phases=Object.fromEntries(['steady','paused','stopped'].map(phase=>{
    const rows=resources.filter(row=>row.phase===phase),span=probe.phases.find(row=>row.name===phase);
    const types=[...new Set(rows.flatMap(row=>Object.keys(row.cpu_by_process_type||{})))];
    return [phase,{duration_ms:span?.end_ms-span?.start_ms,samples:rows.length,
      browser_cpu_percent:distribution(rows.map(row=>row.interval_cpu_percent)),
      summed_process_rss_kib:distribution(rows.map(row=>row.summed_rss_kib)),
      page_js_heap_used_bytes:distribution(rows.map(row=>row.js_heap_used_bytes)),
      cpu_by_process_type:Object.fromEntries(types.map(type=>[type,distribution(rows.map(row=>row.cpu_by_process_type?.[type]))]))}];
  }));
  return {
    startup_ms:{start_click_to_guest_ready:firstReady?firstReady.at_ms-start:null,
      start_click_to_first_varied_frame:firstFrame?firstFrame.committed_ms-start:null,
      runtime_start_to_guest_ready:firstReady?firstReady.at_ms-probe.runtime_start_ms:null},
    steady_capture:{duration_ms:idle.end_ms-idle.start_ms,frames:frames.length,
      frames_per_second:frames.length/((idle.end_ms-idle.start_ms)/1000),
      interval_ms:distribution(frames.slice(1).map((row,index)=>row.at_ms-frames[index].at_ms)),
      request_ms:distribution(frameRequests.map(row=>row.end_ms-row.start_ms)),
      requests:frameRequests.length,requests_per_second:frameRequests.length/((idle.end_ms-idle.start_ms)/1000),
      transferred_pixel_bytes:frames.reduce((sum,row)=>sum+row.pixels_bytes,0),
      distinct_frame_sha256:new Set(frames.map(row=>row.sha256).filter(Boolean)).size,
      new_pixel_frames:framePhases.steady.pixel_change_frames,new_pixel_frames_per_second:framePhases.steady.pixel_change_frames_per_second,
      observer_ms:distribution(frames.map(row=>row.observer_ms)),
      meaning:'delivered framebuffer captures, including repeats; not guest render FPS'},
    input_latency_ms:Object.fromEntries(['down_to_callback_ms','up_to_callback_ms','down_to_visible_commit_ms','up_to_visible_commit_ms','callback_to_visible_commit_ms','up_to_paint_opportunity_ms'].map(key=>[key,distribution(latencies.map(row=>row[key]))])),
    input_trials:latencies,
    frame_phases:framePhases,
    resources:{browser_process_cpu_percent:distribution(resourceRows.map(row=>row.interval_cpu_percent)),
      summed_process_rss_kib:distribution(resourceRows.map(row=>row.summed_rss_kib)),
      renderer_js_heap_used_bytes:distribution(resourceRows.map(row=>row.js_heap_used_bytes)),
      runtime_initial_shared_heap_bytes:probe.receipt?.memoryBytes??null,phase_controls:phases},
  };
}

export async function installPerformanceProbe({moduleURL}) {
  const {PublicQemuRuntime}=await import(moduleURL);
  const probe={phase:'startup',phases:[],requests:[],frames:[],guest_events:[],pointer_events:[],trials:[],states:[],serial:'',serial_carry:'',start_click_ms:null,runtime_start_ms:null,receipt:null};
  const originals={};
  function digest(bytes){let hash=2166136261;for(const byte of bytes){hash^=byte;hash=Math.imul(hash,16777619);}return (hash>>>0).toString(16).padStart(8,'0');}
  probe.roi=()=>{const canvas=document.querySelector('#rawFrameCanvas');if(!canvas?.width)return null;return digest(canvas.getContext('2d').getImageData(20,60,180,40).data);};
  probe.snapshot=()=>{const {runtime,roi,snapshot,setPhase,...data}=probe;return {...data,receipt:runtime?.receipt||probe.receipt};};
  probe.setPhase=name=>{const now=performance.now();if(probe.phases.length)probe.phases.at(-1).end_ms=now;probe.phase=name;probe.phases.push({name,start_ms:now,end_ms:null});};
  probe.setPhase('startup');
  const prototype=PublicQemuRuntime.prototype;
  for(const name of ['start','ask','receive','state'])originals[name]=prototype[name];
  prototype.start=function(...args){probe.runtime=this;probe.runtime_start_ms=performance.now();return originals.start.apply(this,args);};
  prototype.ask=function(op,...args){
    const row={op,phase:probe.phase,start_ms:performance.now(),end_ms:null,ok:null};probe.requests.push(row);
    let result;try{result=originals.ask.call(this,op,...args);}catch(error){row.end_ms=performance.now();row.ok=false;row.error=String(error);throw error;}
    return Promise.resolve(result).then(value=>{row.end_ms=performance.now();row.ok=true;return value;},error=>{row.end_ms=performance.now();row.ok=false;row.error=String(error);throw error;});
  };
  prototype.state=function(status){probe.states.push({at_ms:performance.now(),status});return originals.state.call(this,status);};
  prototype.receive=function(data,...args){
    if(args[0]!==this.generation)return originals.receive.call(this,data,...args);
    const observed=performance.now();
    if(data.type==='serial'){
      probe.serial+=data.value;probe.serial_carry+=data.value;let at;
      while((at=probe.serial_carry.indexOf('\n'))>=0){const line=probe.serial_carry.slice(0,at).trim();probe.serial_carry=probe.serial_carry.slice(at+1);if(line.startsWith('CORES3_WASM ')){try{probe.guest_events.push({at_ms:observed,event:JSON.parse(line.slice(12))});}catch{}}}
    }
    const result=originals.receive.call(this,data,...args);
    if(data.type==='frame'){
      const begin=performance.now(),pixels=data.value.pixels;
      const varied=new Set(Array.from({length:Math.min(400,pixels.length)},(_,i)=>pixels[Math.floor(i*pixels.length/Math.min(400,pixels.length))])).size>8;
      const row={at_ms:observed,committed_ms:performance.now(),phase:probe.phase,sequence:this.sequence,width:data.value.width,height:data.value.height,
        source:data.value.source,source_sequence:data.value.sourceSequence??null,source_updates:data.value.sourceUpdates??null,
        roi_digest:probe.roi(),pixels_bytes:pixels.byteLength,varied,sha256:null,paint_opportunity_ms:null,observer_ms:null};probe.frames.push(row);
      crypto.subtle.digest('SHA-256',pixels).then(value=>{row.sha256=Array.from(new Uint8Array(value),byte=>byte.toString(16).padStart(2,'0')).join('');});
      requestAnimationFrame(()=>requestAnimationFrame(()=>{row.paint_opportunity_ms=performance.now();}));
      row.observer_ms=performance.now()-begin;
    }
    return result;
  };
  document.addEventListener('click',event=>{if(event.target.closest?.('#startBtn'))probe.start_click_ms=performance.now();if(event.target.closest?.('#stopBtn'))probe.stop_click_ms=performance.now();},true);
  for(const type of ['pointerdown','pointerup'])document.addEventListener(type,event=>{if(event.target.id==='rawFrameCanvas')probe.pointer_events.push({type,at_ms:performance.now(),trial:probe.active_trial??null,x:event.clientX,y:event.clientY});},true);
  globalThis.__m5QemuPerformance=probe;
  return {installed:true,roi:{x:20,y:60,width:180,height:40}};
}

// Optional candidate observer. The baseline observer above stays unchanged.
// Find the actual yellow animation glyph in the existing RGB565 framebuffer;
// no host animation or guest/controller substitution is introduced.
export async function installAnimationProbe({moduleURL}) {
  const {PublicQemuRuntime}=await import(moduleURL),probe=globalThis.__m5QemuPerformance;
  if(!probe)throw new Error('Install the performance observer before animation observation');
  probe.animation={roi:{x:20,y:128,width:280,height:24},period_pixels:260,samples:[]};
  const original=PublicQemuRuntime.prototype.receive;
  PublicQemuRuntime.prototype.receive=function(data,...args){
    const active=args[0]===this.generation,result=original.call(this,data,...args);
    if(active&&data.type==='frame'&&data.value.width===320&&data.value.height===240){
      const begin=performance.now(),pixels=data.value.pixels,roi=probe.animation.roi;
      let count=0,sum=0,min=Infinity,max=-Infinity,digest=2166136261;
      for(let y=roi.y;y<roi.y+roi.height;y++)for(let x=roi.x;x<roi.x+roi.width;x++){
        const at=(y*data.value.width+x)*2,value=pixels[at]|pixels[at+1]<<8;
        digest=Math.imul((digest^value)>>>0,16777619);
        if((value>>11&31)>=26&&(value>>5&63)>=35&&(value&31)<=14){count++;sum+=x;min=Math.min(min,x);max=Math.max(max,x);}
      }
      const frame=probe.frames.at(-1);
      probe.animation.samples.push({at_ms:frame.committed_ms,phase:probe.phase,sequence:this.sequence,
        roi_digest:(digest>>>0).toString(16).padStart(8,'0'),yellow_pixels:count,
        centroid_x:count?sum/count:null,min_x:count?min:null,max_x:count?max:null,
        observer_ms:performance.now()-begin});
    }
    return result;
  };
  return {installed:true,...probe.animation.roi};
}

export function summarizeAnimationCurve(probe) {
  if(!probe.animation)return null;
  const period=probe.animation.period_pixels;
  const phases=Object.fromEntries(['steady','input','paused','stopped'].map(phase=>{
    const span=probe.phases.find(row=>row.name===phase),duration=span?(span.end_ms-span.start_ms)/1000:0;
    const samples=probe.animation.samples.filter(row=>row.phase===phase),positions=samples.filter(row=>Number.isFinite(row.centroid_x));
    let previous,unwrapped,wraps=0,changed=0,lastDigest;
    const curve=positions.map(row=>{
      if(previous===undefined)unwrapped=row.centroid_x;
      else{let delta=row.centroid_x-previous;if(delta<-period/2){delta+=period;wraps++;}else if(delta>period/2)delta-=period;unwrapped+=delta;}
      if(lastDigest!==row.roi_digest)changed++;
      previous=row.centroid_x;lastDigest=row.roi_digest;
      return {...row,unwrapped_x:unwrapped};
    });
    const first=curve[0],last=curve.at(-1),elapsed=first&&last?(last.at_ms-first.at_ms)/1000:0;
    const beats=probe.guest_events.filter(row=>row.event.kind==='heartbeat'&&row.at_ms>=(span?.start_ms??Infinity)&&row.at_ms<=(span?.end_ms??-Infinity));
    const a=beats[0],b=beats.at(-1),host=a&&b?b.at_ms-a.at_ms:0;
    return [phase,{duration_seconds:duration,frame_samples:samples.length,glyph_samples:positions.length,
      distinct_roi:new Set(samples.map(row=>row.roi_digest)).size,changed_roi_samples:changed,
      changed_roi_samples_per_second:duration?changed/duration:0,wraps,
      centroid_velocity_pixels_per_host_second:elapsed?(last.unwrapped_x-first.unwrapped_x)/elapsed:null,
      observer_ms:distribution(samples.map(row=>row.observer_ms)),
      clocks:{samples:beats.length,guest_to_host_rate:host?(b.event.elapsed_ms-a.event.elapsed_ms)/host:null,
        lvgl_to_host_rate:host?(b.event.tick_total-a.event.tick_total)/host:null,
        animation_callbacks:beats.length?b.event.animation_samples-a.event.animation_samples:null,
        scheduler_errors:beats.length?Math.max(...beats.map(row=>row.event.scheduler_errors)):null,
        curve:beats.map(row=>({host_ms:row.at_ms-a.at_ms,guest_ms:row.event.elapsed_ms-a.event.elapsed_ms,lvgl_ms:row.event.tick_total-a.event.tick_total,animation_samples:row.event.animation_samples}))},
      curve}];
  }));
  return {roi:probe.animation.roi,period_pixels:period,nominal_guest_velocity_pixels_per_second:100,
    meaning:'Observed yellow glyph centroid and guest UART clocks; framebuffer delivery can repeat pixels and is not optical timing or physical hardware validation',phases};
}
