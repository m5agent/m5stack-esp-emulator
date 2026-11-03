// Test-only readback. Never inject pixels, guest values, input or time.
// Async hashing must not be a waitForFunction predicate: a Promise may be
// treated as truthy before its resolved observation is checked.
const WIDTH=320,HEIGHT=240,SHA256=/^[a-f0-9]{64}$/;
function plain(value){
  if(value===null||typeof value!=='object'||Array.isArray(value))return false;
  try{
    const prototype=Object.getPrototypeOf(value);
    return (prototype===Object.prototype||prototype===null)&&typeof value.then!=='function';
  }catch{return false;}
}
function validOptions(regions,boundary){
  return Array.isArray(regions)&&regions.length===2
    &&regions.every(row=>plain(row)&&typeof row.name==='string'&&row.name.length>0&&row.name.length<=256
      &&typeof row.expected==='string'&&SHA256.test(row.expected)
      &&['x','y','width','height'].every(key=>Number.isInteger(row[key]))
      &&row.x>=0&&row.y>=0&&row.width>0&&row.height>0&&row.x+row.width<=WIDTH&&row.y+row.height<=HEIGHT)
    &&new Set(regions.map(row=>row.name)).size===regions.length
    &&plain(boundary)&&Number.isSafeInteger(boundary.minimumSequence)&&boundary.minimumSequence>=-1
    &&Number.isFinite(boundary.notBeforeMs)&&boundary.notBeforeMs>=0;
}
export function isMatchingCanvasObservation(observation,{regions,boundary}={}){
  if(!validOptions(regions,boundary)||!plain(observation))return false;
  if(!Number.isSafeInteger(observation.frame_sequence)||observation.frame_sequence<=boundary.minimumSequence
      ||!Number.isFinite(observation.captured_ms)||observation.captured_ms<boundary.notBeforeMs)return false;
  if(Object.hasOwn(observation,'width')&&observation.width!==WIDTH
      ||Object.hasOwn(observation,'height')&&observation.height!==HEIGHT)return false;
  if(!Array.isArray(observation.regions)||observation.regions.length!==regions.length
      ||!observation.regions.every(row=>plain(row)&&typeof row.name==='string'&&typeof row.rgba_sha256==='string'&&SHA256.test(row.rgba_sha256))
      ||new Set(observation.regions.map(row=>row.name)).size!==regions.length)return false;
  const actual=new Map(observation.regions.map(row=>[row.name,row.rgba_sha256]));
  // Ignore caller-provided "matched" flags: only measured fields can pass.
  return regions.every(row=>actual.get(row.name)===row.expected);
}
function timeoutError(timeoutMs,lastObservation){
  let serialized;try{serialized=JSON.stringify(lastObservation);}catch{serialized='[not JSON serializable]';}
  const error=new Error('Timed out after '+timeoutMs+'ms waiting for actual canvas pixels. Last observation: '+String(serialized).slice(0,8192));
  error.name='CanvasPixelsTimeoutError';error.lastObservation=lastObservation;return error;
}
export async function waitForCanvasPixels(page,{regions,boundary,timeoutMs=15000,pollingMs=100}={}){
  if(!validOptions(regions,boundary))throw new TypeError('Expected two unique named bounded regions with SHA256 values and a finite frame/time boundary');
  if(!page||typeof page.evaluate!=='function')throw new TypeError('A page with evaluate() is required');
  if(!Number.isFinite(timeoutMs)||timeoutMs<=0||!Number.isFinite(pollingMs)||pollingMs<0)
    throw new RangeError('Pixel timeout must be positive and polling interval nonnegative');
  // Browser sampling gets coordinates/names, never expected hash values.
  const sampleRegions=regions.map(({name,x,y,width,height})=>({name,x,y,width,height}));
  const deadline=performance.now()+timeoutMs;
  let lastObservation=null;
  while(true){
    const remaining=deadline-performance.now();
    if(remaining<=0)throw timeoutError(timeoutMs,lastObservation);
    let timer;
    try{
      lastObservation=await Promise.race([
        page.evaluate(async({regions})=>{
          const canvas=document.querySelector('#rawFrameCanvas');
          const frame_sequence=Number(document.querySelector('#deviceMount')?.dataset.frameSequence);
          const captured_ms=performance.now();
          if(!canvas||canvas.width!==320||canvas.height!==240)
            return {status:'unavailable',reason:'Native canvas must be320x240',frame_sequence,captured_ms};
          const context=canvas.getContext('2d');
          if(!context)return {status:'unavailable',reason:'Native canvas has no2d context',frame_sequence,captured_ms};
          // One synchronous snapshot before any digest. Neither ROI can see
          // a new renderer frame that arrives during asynchronous hashing.
          const snapshot=context.getImageData(0,0,320,240).data,observed=[];
          for(const row of regions){
            const pixels=new Uint8Array(row.width*row.height*4);
            for(let y=0;y<row.height;y++)
              pixels.set(snapshot.subarray(((row.y+y)*320+row.x)*4,((row.y+y)*320+row.x+row.width)*4),y*row.width*4);
            const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels)),byte=>byte.toString(16).padStart(2,'0')).join('');
            observed.push({name:row.name,rgba_sha256:hash});
          }
          return {frame_sequence,captured_ms,width:320,height:240,regions:observed};
        },{regions:sampleRegions}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(timeoutError(timeoutMs,lastObservation)),remaining);}),
      ]);
    }catch(error){
      if(error?.name==='CanvasPixelsTimeoutError')throw error;
      const failure=new Error('Actual canvas evaluation failed: '+String(error?.message||error),{cause:error});
      failure.lastObservation=lastObservation;throw failure;
    }finally{clearTimeout(timer);}
    if(isMatchingCanvasObservation(lastObservation,{regions,boundary}))return lastObservation;
    const nextRemaining=deadline-performance.now();
    if(nextRemaining<=0)throw timeoutError(timeoutMs,lastObservation);
    await new Promise(done=>setTimeout(done,Math.min(pollingMs,nextRemaining)));
  }
}
