import {distribution} from './public_qemu_performance.mjs';

// One algorithm for old raw observations and new benchmark runs. Reconstruct
// serial independently by port and retain the frame gap crossing window start.
export function summarizeEmulatorRun(r) {
  const firstFrame=r.frames.find(f=>f.nonblack_channels),first=r.sample_start_ms,last=r.sample_end_ms;
  const frames=r.frames.filter(f=>f.at_ms>=first&&f.at_ms<=last),duration=(last-first)/1000;
  let previous=r.frames.filter(f=>f.at_ms<first).at(-1)?.digest,changed=0;
  for(const frame of frames){if(frame.digest!==previous)changed++;previous=frame.digest;}
  const values=r.states.filter(s=>s.at_ms>=first&&s.at_ms<=last);
  const cues=[],lines=new Map();
  for(const e of r.serial_events){
    if(e.source==='emulator'||e.source==='uart1')continue;
    let line=lines.get(e.source)||'';
    for(const c of e.data){
      if(c==='\n'){
        const clean=line.match(/(?:DANCE |StackChan auto-dance |phase=).*$/)?.[0];
        if(clean)cues.push({at_ms:e.at_ms,source:e.source,line:clean.trim()});
        line='';
      }else line+=c;
    }
    lines.set(e.source,line);
  }
  const previousFrame=r.frames.filter(f=>f.at_ms<first).at(-1);
  const gaps=frames.map((f,i)=>{const previous=i?frames[i-1]:previousFrame;return previous?f.at_ms-previous.at_ms:null;}).filter(Number.isFinite);
  const guestStats=r.stats.filter(s=>Number.isFinite(s.speed));
  const danceCues=cues.filter(c=>/^DANCE cue=\d+/.test(c.line));
  const precedingState=r.states.filter(s=>s.at_ms<=first).at(-1),baseline=precedingState??values[0];
  const finalState=values.at(-1)??baseline;
  const packets=s=>Number.isFinite(s?.state?.packets)?s.state.packets:null;
  const initialPackets=packets(baseline),finalPackets=packets(finalState);
  const vector=s=>{
    if(!Array.isArray(s?.state?.servos)||s.state.servos.length===0)return null;
    const positions=s.state.servos.map(servo=>({id:String(servo.id),
      unit:Number.isFinite(servo.present_position)?'raw-ticks':'degrees',
      value:Number.isFinite(servo.present_position)?servo.present_position:servo.positionDegrees}));
    if(!positions.every(p=>Number.isFinite(p.value))||new Set(positions.map(p=>p.id)).size!==positions.length)return null;
    positions.sort((a,b)=>a.id.localeCompare(b.id));return JSON.stringify(positions);
  };
  let previousPosition=vector(baseline),positionChanges=0;
  for(const observation of values){const next=vector(observation);if(next===null)continue;
    if(previousPosition!==null&&next!==previousPosition)positionChanges++;previousPosition=next;
  }
  const rendered=r.render_trace_installed===false?undefined:r.render_poses?.filter(p=>p&&p.at_ms>=first&&p.at_ms<=last&&p.dom?.known==='true'
    &&Number.isFinite(p.yaw?.angleDeg)&&Number.isFinite(p.pitch?.angleDeg));
  let previousPose=null,renderedChanges=0;
  for(const pose of rendered||[]){
    const actual=JSON.stringify([pose.yaw.angleDeg,pose.pitch.angleDeg]);
    if(previousPose!==null&&actual!==previousPose)renderedChanges++;
    previousPose=actual;
  }
  const renderedTrace=rendered?{source:'actual-workbench-viewer-render',observations:rendered.length,
    actual_angle_changes:renderedChanges,
    intermediate_observations:rendered.filter(p=>[p.yaw,p.pitch].some(j=>j.transitioning
      &&Number.isFinite(j.targetAngleDeg)&&Math.abs(j.angleDeg-j.targetAngleDeg)>1e-6)).length,
    render_gap_ms:distribution(rendered.slice(1).map((p,i)=>p.at_ms-rendered[i].at_ms)),
    observer_ms:distribution(rendered.map(p=>p.observer_ms)),
    meaning:'Angles are read from real joint getState() in the actual viewer render callback. Targets are not substituted for rendered poses. This is a visual model trace, not mechanical or physical servo evidence.'}:null;
  return {startup_ms:{first_serial:r.first_serial_ms===null?null:r.first_serial_ms-r.start_ms,
      ready_marker:r.ready_ms===null?null:r.ready_ms-r.start_ms,first_nonblack_frame:firstFrame?firstFrame.at_ms-r.start_ms:null,
      runtime_preparation:r.runtime_start_ms===undefined?null:r.runtime_start_ms-r.start_ms},
    steady:{duration_seconds:duration,delivered_frames:frames.length,delivered_fps:frames.length/duration,
      pixel_change_frames:changed,pixel_change_fps:changed/duration,frame_gap_ms:distribution(gaps),
      state_updates:values.length,state_gap_ms:distribution(values.slice(1).map((s,i)=>s.at_ms-values[i].at_ms)),
      frame_observer_ms:distribution(frames.map(f=>f.observer_ms)),
      dance_cue_count:danceCues.filter(c=>c.at_ms>=first&&c.at_ms<=last).length,
      packet_delta:initialPackets===null||finalPackets===null?null:finalPackets-initialPackets,
      packet_window:{baseline_source:baseline?(precedingState?'at-or-before-window':'first-in-window'):null,
        first_observed_at_ms:baseline?.at_ms??null,initial_packets:initialPackets,final_packets:finalPackets},
      position_change_observations:positionChanges,rendered_joint_trace:renderedTrace},
    servo_last_state:r.states.at(-1)?.state??null,guest_speed:distribution(guestStats.map(s=>s.speed)),
    serial_cues:cues,all_observed_dance_cue_count:danceCues.length,
    meaning:'Delivered callbacks and actual pixel changes; neither is physical display FPS. State callbacks are real controller observations, not interpolated poses. UART markers are reconstructed per source port. Position-change counts compare successive same-lane id/position vectors only; raw ticks and degrees are never numerically compared between engines.'};
}
