import {renderSerialChannelSelect} from './serial-channel-state.js';
import {renderUIFlowCloudStatus} from './uiflow-cloud-status.js';
import {composeUIFlowWorkbenchFirmware,loadUIFlowWorkbenchProfiles} from './public-uiflow-firmware.js';
import {PublicMicroPythonRunner} from './public-micropython.js';
import {assetUrl, siteRoot, parseLaunchConfig, buildShareUrl, normalizeServiceUrl, selectExecutionLane} from './public-config.js';
import {downloadFirmware, normalizeFirmwareSha256, DEFAULT_MAX_FIRMWARE_BYTES, sha256Buffer} from './public-firmware.js';
import {PublicDeviceService, deviceIdentityCapability} from './public-service.js';
import {PublicBrowserRuntime, getBrowserProfile} from './public-browser-runtime.js';
import {PublicQemuRuntime, browserQemuHistory} from './public-qemu-runtime.js';
import {composeDemoFirmware, composeWallclockDemoFirmware, DEMO_FIRMWARE, WALLCLOCK_DEMO_FIRMWARE} from './public-demo-firmware.js';
import {loadQemuBrowserProfiles,getQemuBrowserProfile,resolveQemuFirmwareProfile,advanceQemuEncoderTarget} from './public-qemu-profiles.js';
import {composeQemuProbeFirmware} from './public-qemu-probe-firmware.js';
import {qemuOnboardVisualCommands} from './public-qemu-frame.js';
import {qemuServoVisualCommands,qemuServoDiagnostic} from './public-qemu-servo.js';
import {ensurePublicIsolation} from './public-coi.js';
import {PublicSessionController} from './public-session-controller.js';
import {createDeviceShell} from './device-shell-factory.js';
import {createVisualModelShell} from './model-shell.js';
import {createPublicUnitAssembly} from './public-unit-assembly.js';
import {PublicServiceProgram} from './public-service-program.js';

const $ = (id) => document.getElementById(id),
  root = siteRoot();
const state = {
  devices: [],
  units: [],
  config: {},
  selected: null,
  shell: null,
  selection: 0,
  runGeneration: 0,
  openGeneration: 0,
  serviceGeneration: 0,
  serviceSessionsGeneration: 0,
  run: null,
  abort: null,
  service: null,
  serviceDevices: [],
  inventory: null,
  picker: null,
  busy: false,
  serial: '',
  serialBytes: 0,
  deviceFilter: 'all',
  unitFilter: 'all',
  selectedUnit: null,
  unitShell: null,
  unitPreviewGeneration: 0,
  browserModelsPaused: false,
  holds: new Map(),
  stopped: false,
};
const node = (tag, className, value) => {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (value != null) n.textContent = value;
  return n;
};
const bytes = (size) => (size >= 1048576 ? `${(size / 1048576).toFixed(1)} MiB` : `${size} B`);
const source = () => document.querySelector('input[name="firmwareSource"]:checked').value;
const active = (run) => run && run === state.run && run.generation === state.runGeneration && !run.stopping;
function message(id, text = '') {
  $(id).textContent = text;
  $(id).hidden = !text;
}
function error(error) {
  if (error?.name !== 'AbortError') message('errorBanner', error?.message || String(error));
}
function browserProfile(id) {
  if (state.config.browser_board_execution !== true || state.browserUnavailable) return null;
  if (state.config.browser_runtime_engine === 'qemu-wasm') return state.qemuProfiles ? getQemuBrowserProfile(id,state.qemuProfiles,{allowCandidateProfiles:state.config.publication_eligible===false}) : null;
  return getBrowserProfile(id);
}
function reference(device = state.selected) {
  const profile=browserProfile(device?.id);
  if ($('referenceExample').value==='uiflow-cloud') {
    const startup=serviceCloudStartup(device?.id);
    return startup ? {name:`${device.name} · 官方 UIFlow2 · 云端配对`,nativeCloud:true,sha256:startup.reference_sha256} : null;
  }
  if (lane(device)==='service' && serviceProgrammingDevice(device?.id) && $('referenceExample').value==='uiflow')
    return {name:`${device.name} · 本地 MicroPython 编程`,nativeWorkbench:true};
  const workbench=state.workbenchProfiles?.profiles.find(row=>row.deviceId===device?.id);
  if(profile&&workbench&&$('referenceExample').value==='uiflow')return {name:`${device.name} · 本地 MicroPython 编程`,composedWorkbench:true,sha256:workbench.firmwareSHA256};
  if (['xtensa-board-display-v1','xtensa-board-led-v1','riscv-board-display-v1'].includes(profile?.fixture?.id)) return {
    name:`${device.name} ${profile.display===null?'RGB 与按键':'屏幕与输入'}示例`,composedProbe:true,sha256:profile.fixture.firmwareSHA256};
  if (device?.id === 'cores3' && state.config.browser_runtime_engine === 'qemu-wasm') {
    if (state.config.browser_wallclock_example && $('referenceExample').value === 'wallclock-candidate')
      return {name:'CoreS3 LVGL + PIR（正常速度，候选修复）',composed:true,wallclockCandidate:true,
        sha256:WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256};
    return {name:'CoreS3 LVGL + PIR（原始程序，正常时钟）',composed:true,sha256:DEMO_FIRMWARE.firmwareSHA256};
  }
  return (
    (state.config.browser_runtime_engine !== 'qemu-wasm' && device?.browser?.reference) ||
    (device?.uiflow2?.firmware?.download_url
      ? {url: device.uiflow2.firmware.download_url, name: `UIFlow2 ${device.uiflow2.firmware.version}`}
      : null)
  );
}
function serviceProgrammingDevice(id=state.selected?.id) {
  return state.serviceDevices.some(row=>row.device_id===id&&row.creatable&&row.program_modes?.includes('uiflow-live'));
}
function serviceCloudStartup(id=state.selected?.id) {
  const row=state.serviceDevices.find(row=>row.device_id===id&&row.creatable), startup=row?.uiflow_startup;
  return startup?.modes?.includes('cloud')&&startup.runtime==='qemu-wifi'&&/^[a-f0-9]{64}$/.test(startup.reference_sha256||'') ? startup : null;
}
function serviceCloudIdentity(id=state.selected?.id) {
  const capability=deviceIdentityCapability(state.serviceDevices.find(row=>row.device_id===id&&row.creatable),'qemu-wifi');
  return capability?.selectors.includes('key')&&capability.selectors.includes('mac')&&capability.cloud_default==='persistent-key';
}
function updateReferenceDefault() {
  if (!state.referenceExplicit && source()==='reference' && !$('firmwareSha').value.trim())
    $('referenceExample').value=serviceCloudStartup()&&!['browser','model'].includes($('runtimeMode').value)?'uiflow-cloud':'uiflow';
}
function selectedAttachments() {
  try {
    return state.picker?.attachments(state.selected?.id) || [];
  } catch {
    return [];
  }
}
function lane(device = state.selected) {
  const mode = $('runtimeMode').value;
  if (source()==='reference' && $('referenceExample').value==='uiflow-cloud' && mode!=='model')
    return mode!=='browser'&&serviceCloudStartup(device?.id)?'service':null;
  const serviceReady = state.serviceDevices.some((item) => item.device_id === device?.id && item.creatable);
  return selectExecutionLane({mode,serviceReady,browserAvailable:!!browserProfile(device?.id),
    hasAttachments:selectedAttachments().length>0});
}
function deviceRuntimeLabel(device) {
  if (browserProfile(device?.id)) return '浏览器运行';
  if (
    state.serviceDevices.some(
      (item) => item.device_id === device?.id && item.creatable,
    )
  )
    return '服务可运行';
  if (device?.visual_only || (state.config.browser_runtime_engine === 'qemu-wasm' && device?.browser_only)) return '仅模型';
  return '连接服务';
}
function showSerialView(view) {
  state.serial = view.text; state.serialBytes = view.bytes;
  $('serialOutput').textContent = view.text; $('serialCount').textContent = bytes(view.bytes);
  renderSerialChannelSelect($('serialChannel'), {view: () => view});
  if ($('serialDrawer').open) $('serialOutput').scrollTop = $('serialOutput').scrollHeight;
}

function appendSerial(text) {
  if (!text) return;
  state.serialBytes += new TextEncoder().encode(text).byteLength;
  state.serial = (state.serial + text).slice(-65536);
  $('serialOutput').textContent = state.serial;
  $('serialCount').textContent = bytes(state.serialBytes);
  if ($('serialDrawer').open) $('serialOutput').scrollTop = $('serialOutput').scrollHeight;
}
function updateBrowserBoot(value) {
  const label=$('browserBootStatus'), boot=value?.boot;
  const next={assetsReady:String(boot?.assetsReady??false),guestStarted:String(boot?.guestStarted??false),
    firstFrameSequence:String(boot?.firstFrameSequence??''),applicationReady:boot?.applicationReady??'unknown'};
  Object.assign(label.dataset,next);
  if(!boot) { message('browserBootStatus'); return; }
  const ended=['stopped','error'].includes(value.status);
  let phase;
  if(boot.guestStarted)phase='客体已开始执行';
  else if(boot.assetsReady)phase=ended?'WASM 和 ROM 已就绪，客体未开始执行':'WASM 和 ROM 已就绪，正在启动客体';
  else phase=ended?'WASM 和 ROM 未就绪':'正在准备 WASM 和 ROM';
  const frame=boot.firstFrameSequence!==null?'首帧已收到':value.runtime?.frameTransport===null?'设备无屏幕':ended?'未取得首帧':'等待首帧';
  const app={confirmed:'已收到应用就绪标记',waiting:ended?'未收到应用就绪标记':'等待应用就绪标记',unknown:'应用就绪未确认'};
  const text=`${phase} · ${frame} · ${app[boot.applicationReady]}`;
  if(label.textContent!==text)message('browserBootStatus',text);
}
function updateFirmwareIdentity(receipt) {
  $('firmwareIdentity').hidden=!receipt;
  $('firmwareInputSha256').textContent=receipt?.firmwareInputSha256??'';
  $('firmwareRuntimeSha256').textContent=receipt?.firmwareRuntimeSha256??'';
  if(!receipt) { $('firmwareNormalization').textContent=''; return; }
  const {kind,inputBytes,runtimeBytes}=receipt.normalization;
  $('firmwareNormalization').textContent=kind==='pad-ff'
    ?`运行前用 0xFF 从 ${bytes(inputBytes)} 补齐到 ${bytes(runtimeBytes)}。`
    :`输入已达到 ${bytes(runtimeBytes)} Flash 容量，直接使用。`;
}
function browserEvidenceState(status,text) {
  $('browserEvidenceStatus').dataset.evidenceState=status;
  message('browserEvidenceStatus',text);
}
function updateBrowserEvidence() {
  const controller=state.lastBrowserController;
  const ready=!!controller?.receipt;
  $('browserEvidenceBtn').hidden=!ready;
  const label=$('browserEvidenceStatus');
  const session=ready?controller.sessionId:'';
  if(label.dataset.sessionId===session)return;
  label.dataset.sessionId=session;
  browserEvidenceState(ready?'ready':'unavailable',ready?'本地运行记录可下载。':'');
}
function status(status, detail, session = state.run?.controller?.current) {
  const labels = {
    loading: '正在加载固件',
    booting: '设备启动中',
    provisioning: '正在创建设备',
    flashing: '正在写入固件',
    running: '固件运行中',
    paused: '固件已暂停',
    sleeping: '设备睡眠中',
    stopped: '运行已停止',
    stopping: '正在停止会话',
    stop_pending: '停止结果未确认',
    error: '运行未完成',
    model: '模型预览',
  };
  $('runtimeStatus').replaceChildren(node('i'), document.createTextNode(labels[status] || status));
  $('runtimeStatus').dataset.status = status;
  if (detail) $('frameStatus').textContent = detail;
  renderUIFlowCloudStatus($('uiflowCloudStatus'), session, {cloudExpected: !!state.run?.cloudStartup});
  updatePythonControls(status);
  $('pauseBtn').hidden = !state.run || state.run.kind !== 'browser' || !['running', 'paused'].includes(status);
  $('pauseBtn').textContent = status === 'paused' ? '继续' : '暂停';
  $('nativeScreenBtn').hidden = !(state.run?.controller instanceof PublicQemuRuntime && state.run.controller.profile?.display);
  $('browserPirPanel').hidden = !(state.run?.controller instanceof PublicQemuRuntime && !!state.run.controller.profile?.inputs.pir);
  $('browserPir').disabled = status !== 'running';
  updateBrowserEvidence();
  $('stopBtn').hidden = !state.run;
  $('stopBtn').textContent = state.stopUnconfirmed ? '重试停止' : state.run?.owned===false ? '停止查看' : '停止';
}
const pythonPhases={connecting:'正在连接 MicroPython…',uploading:'正在传输代码…',running:'代码正在运行',complete:'运行完成',error:'代码执行出现异常',interrupted:'已中断',failed:'运行未完成',noRepl:'当前固件未响应网页 MicroPython REPL 握手'};
function pythonUnavailableReason() {
  const device=state.selected;
  if (state.run?.cloudStartup || state.run?.controller?.current?.uiflow_startup?.mode==='cloud')
    return '官方 UIFlow2 云端配对模式：在设备屏幕查看配对码，完成绑定后通过 UIFlow 编程。网页编辑器请另选“本地 MicroPython 编程”。';
  if (state.run?.kind==='service') return '当前固件未启用网页编程。选择“本地 MicroPython 编程”后重新启动。';
  if (lane()==='service'&&serviceProgrammingDevice()) return '启动本地 MicroPython 编程环境后即可运行代码';
  if(device?.uiflow2?.supported===false)return '此型号不支持 UIFlow2，当前网页编程不可用';
  if(device?.visual_only || (state.config.browser_runtime_engine==='qemu-wasm'&&device?.browser_only&&!browserProfile(device.id)))
    return '当前浏览器仅提供此型号的模型预览，不能运行网页代码';
  if(state.browserUnavailable||state.config.browser_board_execution!==true)return '本站浏览器运行暂不可用，可浏览模型或连接仿真服务';
  if(!browserProfile(device?.id))return '此型号尚未取得浏览器运行准入，网页编程不可用';
  if(state.config.browser_runtime_engine!=='qemu-wasm')return '当前运行内核不提供网页 MicroPython 编程';
  return '启动浏览器中的本地 MicroPython 编程环境后即可运行';
}
function updateStageFirmwareNotice(currentStatus, uiflowReady) {
  const starting = ['loading', 'provisioning', 'flashing', 'booting'].includes(currentStatus);
  const cloud=state.run?.cloudStartup || state.run?.controller?.current?.uiflow_startup?.mode==='cloud';
  const cloudWaiting=cloud&&currentStatus==='running'&&!state.run?.controller?.frameReady;
  const phase = cloud&&(starting||cloudWaiting) ? 'cloud-starting' : starting ? 'starting' : currentStatus === 'running' && uiflowReady ? 'ready' : '';
  const notice = $('stageFirmwareNotice');
  if (notice.dataset.phase === phase) return;
  notice.dataset.phase = phase;
  notice.hidden = !phase;
  $('stageFirmwareTitle').textContent = phase==='cloud-starting' ? '正在启动官方 UIFlow2' : starting ? '正在启动固件' : phase ? 'MicroPython 已就绪' : '';
  const readyDetail = state.selected?.display
    ? '现在可以运行 MicroPython。程序绘图后，设备屏幕会更新。'
    : '现在可以运行 MicroPython，并在下方查看代码输出。';
  $('stageFirmwareDetail').textContent = phase==='cloud-starting' ? '正在等待设备画面。联网与配对状态以固件屏幕和串口为准。' : starting ? '正在准备设备，请稍候。' : phase ? readyDetail : '';
  $('stageFirmwareEditor').hidden = phase !== 'ready';
}
function updatePythonControls(currentStatus=state.run?.controller?.status || state.run?.controller?.current?.state) {
  const run=state.run, native=active(run)&&run.kind==='service'&&!!run.python;
  if (!active(run) || run.kind !== 'service' || !run.controller.current) $('serialChannel').disabled = true;
  const supported=active(run)&&(run.controller instanceof PublicQemuRuntime&&run.controller.profile?.inputs.uart || native&&(run.python.ready||run.python.busy));
  const programming=!!run?.controller?.receipt?.uiflowWorkbench&&state.workbenchProfiles?.profiles.some(row=>
    row.deviceId===state.selected?.id&&row.deviceId===run.controller.receipt.deviceId
      &&row.firmwareSHA256===run.controller.receipt.firmwareSha256);
  const pythonBusy=!!run?.python?.busy,busy=pythonBusy||!!run?.serialSending;
  const replace=pythonBusy&&run.python.canReplace===true&&run.pythonPhase==='running';
  $('pythonRunBtn').disabled=!supported||currentStatus!=='running'||busy&&!replace;
  $('pythonInterruptBtn').disabled=!supported||currentStatus!=='running'||!pythonBusy||run.pythonPhase!=='running'||run.python?.canInterrupt===false;
  $('pythonInterruptBtn').title=run?.python?.canInterrupt===false?'此旧会话不提供中断；新建 UIFlow 编程环境可使用中断。':'';
  $('pauseBtn').disabled=!!run?.serialSending||pythonBusy&&run.pythonPhase!=='running';
  $('serialInput').disabled=$('serialSendBtn').disabled=!!native||!supported||currentStatus!=='running'||busy;
  if(native&&!supported)$('pythonStatus').textContent='正在同步服务中的 UIFlow 编程环境…';
  else if(!supported)$('pythonStatus').textContent=pythonUnavailableReason();
  else if(currentStatus==='paused')$('pythonStatus').textContent='设备已暂停，请先继续';
  else if(currentStatus==='error')$('pythonStatus').textContent='设备运行未完成，请停止或重新启动';
  else if(currentStatus==='sleeping')$('pythonStatus').textContent='设备已休眠，请唤醒后运行代码';
  else if(currentStatus==='booting')$('pythonStatus').textContent=programming?'正在启动 MicroPython…':'正在启动固件…';
  else if(currentStatus==='running')$('pythonStatus').textContent=pythonPhases[run.pythonPhase]||(native||programming?'MicroPython 已就绪':'当前固件的 MicroPython REPL 未验证，运行代码时尝试连接');
  const readyWorkbench = currentStatus === 'running' && supported && (programming || (native && run.owned !== false && run.python.ready));
  updateStageFirmwareNotice($('runtimeStatus').dataset.status, readyWorkbench && !busy && !run.pythonPhase);
}
async function runPython() {
  const run=state.run;
  if(!active(run)||(!(run.controller instanceof PublicQemuRuntime)&&!run.python))return;
  run.python ||= new PublicMicroPythonRunner(run.controller);
  if(run.python.busy&&!(run.python.canReplace===true&&run.pythonPhase==='running')||run.serialSending)return;
  const click=run.pythonClick=(run.pythonClick||0)+1,current=()=>active(run)&&run.pythonClick===click;
  $('pythonOutput').textContent='';
  try {
    await run.python.run($('pythonSource').value,{
      onPhase:phase=>{if(current()){run.pythonPhase=phase;$('pythonStatus').textContent=pythonPhases[phase];updatePythonControls();}},
      onOutput:text=>{if(current()){const out=$('pythonOutput');out.textContent=(out.textContent+text).slice(-65536);out.scrollTop=out.scrollHeight;}},
    });
  }catch(cause){if(current()){
    run.pythonPhase=cause.code==='micropython_repl_timeout'?'noRepl':'failed';
    $('pythonStatus').textContent=pythonPhases[run.pythonPhase];
    $('pythonOutput').textContent+=`\n${cause.message}`;
  }}finally{if(current())updatePythonControls();}
}
function updateCapability() {
  const device = state.selected,
    selectedLane = lane(),
    supported = !!browserProfile(device?.id),
    modelOnly = device?.visual_only || (state.config.browser_runtime_engine==='qemu-wasm'&&device?.browser_only&&!supported);
  $('capabilityTitle').textContent =
    selectedLane === 'browser'
      ? '浏览器本地运行'
      : selectedLane === 'service'
        ? '通过仿真服务运行'
        : selectedLane === 'model'
          ? '仅浏览模型'
          : modelOnly
            ? '仅浏览模型'
            : supported
              ? '请选择浏览器运行'
              : '此设备需要仿真服务';
  $('capabilityText').textContent =
    selectedLane === 'browser'
      ? '固件在当前浏览器中执行，屏幕与串口来自模拟器。不同固件的兼容性仍有边界。'
      : selectedLane === 'service'
        ? '固件运行在你连接的原生设备服务中，画面与输入绑定本次会话。'
        : selectedLane === 'model'
          ? '可旋转、缩放并探索模型；本模式不执行固件。'
          : modelOnly
            ? '当前浏览器尚未接入本型号的固件运行。可旋转、缩放并探索模型。'
            : '现在可以浏览 3D 模型。连接兼容服务后，可启动此设备的固件。';
  if (selectedLane === 'browser' && state.config.browser_runtime_engine==='qemu-wasm') {
    let p=browserProfile(device?.id);
    const runningProfile=active(state.run)&&state.run.controller instanceof PublicQemuRuntime
      ?state.run.controller.profile:null;
    const referenceHash=source()==='reference'?reference(device)?.sha256:null;
    if (runningProfile?.deviceId===device?.id) p=runningProfile;
    else if (p&&referenceHash) p=resolveQemuFirmwareProfile(p,referenceHash);
    const wallclock=p?.firmwareVariant?.schedulerCandidate==='sdk-python-single-schedule-v1';
    $('capabilityText').textContent=`C/QEMU 在浏览器执行 ${device.name}。${p?.admission==='candidate'?'候选预览，尚未公开准入。':''}${wallclock?'本示例采用正常时钟和 LVGL 调度候选修复。':p?.clockDivisor>1?`虚拟时间与看门狗按 1/${p.clockDivisor} 慢放。`:'采用正常虚拟时钟。'}刷新不保存 Flash。`;
    if (p?.display===null) $('capabilityText').textContent += '无屏设备，RGB 与按键状态从本次模拟器读取。';
  }
  if (source()==='reference' && $('referenceExample').value==='uiflow-cloud') {
    $('capabilityTitle').textContent=selectedLane==='service'?'官方 UIFlow2 · 原生服务运行':'云端配对需要原生设备服务';
    $('capabilityText').textContent=selectedLane==='service'
      ? '设备运行官方启动界面，并自行连接 UIFlow 云端。配对状态请查看设备屏幕。'
      : '请连接支持此型号云端启动的服务并选择自动或服务运行；浏览器编程请选择“本地 MicroPython 编程”。';
  }
  if (selectedAttachments().length && !['service','model'].includes(selectedLane)) {
    $('capabilityTitle').textContent = '所选 Unit 需要服务运行';
    $('capabilityText').textContent = '浏览器内核尚未接入这些 Unit。请选择自动或服务运行，或取消已连接的 Unit。';
  }
  const assembly=state.picker?.snapshot?.(),invalidAssembly=assembly?.valid===false;
  if(invalidAssembly){
    $('capabilityTitle').textContent='请调整 Unit 连线';
    $('capabilityText').textContent=assembly.issues?.[0]?.message||'当前装配草稿与设备接口不兼容。';
  }
  $('openServiceBtn').hidden = !!selectedLane || !!modelOnly || $('runtimeMode').value === 'browser';
  $('startBtn').disabled = state.busy || state.stopUnconfirmed || invalidAssembly || !device || !state.shell || !selectedLane;
  $('startBtn').textContent =
    selectedLane === 'model' ? '浏览设备模型 →' : state.busy ? '正在加载…' : state.run ? '重新运行 →' : '开始运行 →';
  $('cancelLoadBtn').hidden = !state.busy;
  $('addSelectedUnitBtn').disabled=!state.selectedUnit||state.busy||!!state.run;
  const identitySupported=serviceCloudIdentity();
  $('cloudIdentityFields').hidden = source() !== 'reference' || !reference()?.nativeCloud || selectedLane !== 'service' || !identitySupported;
  $('cloudIdentityMac').disabled = state.busy || !!state.run || !identitySupported;
}
function renderDevices() {
  const query = $('search').value.trim().toLowerCase();
  const filtered = state.devices.filter(
    (d) =>
      `${d.name} ${d.id} ${d.sku || ''} ${d.hardware?.soc || d.group_label || ''}`.toLowerCase().includes(query) &&
      (state.deviceFilter !== 'browser' || browserProfile(d.id)),
  );
  $('deviceNav').replaceChildren();
  for (const device of filtered) {
    const item = node('button', 'device-choice');
    const runtimeLabel = deviceRuntimeLabel(device);
    item.type = 'button';
    item.dataset.deviceId = device.id;
    item.setAttribute('aria-pressed', String(state.selected?.id === device.id));
    item.append(node('strong', '', device.name));
    item.append(
      node(
        'small',
        browserProfile(device.id) ? 'browser-marker' : '',
        `${device.sku || device.group_label || 'M5Stack'} · ${runtimeLabel}`,
      ),
    );
    item.addEventListener('click', () => void selectDevice(device.id).catch(error));
    $('deviceNav').append(item);
  }
  if (!filtered.length) $('deviceNav').append(node('p', 'empty-list', '没有匹配设备。试试产品名或 SKU。'));
  $('deviceResults').textContent = `${filtered.length} 个匹配设备`;
}
function renderDetails() {
  const device = state.selected,
    list = node('dl');
  const qemu=state.config.browser_runtime_engine==='qemu-wasm',profile=browserProfile(device?.id);
  const legacy=qemu?null:device.browser;
  const workbench=state.workbenchProfiles?.profiles.some(row=>row.deviceId===device.id);
  const range=qemu
    ? profile?(workbench?'浏览器本地运行 · MicroPython 编程':'浏览器候选预览 · 屏幕与按键示例')
      : device.visual_only||device.browser_only?'当前浏览器仅供模型预览':'浏览器尚未准入；需连接支持本型号的仿真服务'
    : legacy?.description||device.runtime?.execution||'独立视觉模型';
  const limits=[...(legacy?.limitations||[]),...(device.runtime?.blockers||[])];
  if(qemu&&device.browser_only&&!profile)limits.unshift('此型号的旧浏览器演示不属于当前运行内核，当前站点不提供其固件运行。');
  if(qemu&&profile)limits.unshift('完整 UIFlow2 API、任意固件及物理硬件行为未验证。');
  if(qemu&&profile&&['stopwatch','sticks3','papercolor','papermono'].includes(device.id))
    limits.unshift('模型电源键遵循 PM1 应用配置；接收 BtnPWR 事件需在应用中配置按键事件模式。');
  if(device.uiflow2?.supported===false)limits.unshift('此型号不支持 UIFlow2，当前网页编程不可用。');
  if(device.runtime?.reason)limits.push(device.runtime.reason);
  const display = device.hardware?.display || device.display;
  for (const [label, value] of [
    ['芯片', device.hardware?.soc || device.group_label],
    [
      '屏幕',
      display ? `${display.width} × ${display.height} · ${display.driver || display.type || ''}` : '无板载显示屏',
    ],
    ['运行范围', range],
  ])
    if (value) list.append(node('dt', '', label), node('dd', '', value));
  $('deviceDetails').replaceChildren(list);
  for (const text of limits)
    $('deviceDetails').append(node('p', '', text));
  const ref = reference();
  $('referenceExampleFields').hidden = !serviceCloudStartup() && !serviceProgrammingDevice() && (!profile || !qemu || !workbench);
  for(const option of $('referenceExample').options)option.hidden=option.value==='uiflow-cloud'
    ? !serviceCloudStartup() : ['wallclock-candidate','stock-div8'].includes(option.value)&&device?.id!=='cores3';
  $('referenceTitle').textContent = ref?.name || '此型号暂无参考固件';
  $('referenceDescription').textContent = ref?.nativeCloud
    ? '保留官方 UIFlow2 开机流程，在原生服务中联网申请配对码。请在设备屏幕查看云端返回的配对码。'
    : ref?.nativeWorkbench
    ? '通过当前服务运行 MicroPython，Unit、屏幕和网页代码共用同一设备会话。此编程启动环境不运行官方云端配对界面。'
    : ref?.composedWorkbench
    ? '官方 UIFlow2 运行时配网页编程启动脚本，就绪后可在下方运行 MicroPython；不运行官方云端配对界面。'
    : ref?.wallclockCandidate
    ? '在官方 UIFlow2 基底中加入明确的 LVGL 调度候选修复，用于本交互示例。'
    : ref?.composedProbe
    ? ({'cardputer-adv':'点击模型键盘，或先点击模型再用电脑键盘输入；屏幕显示按键状态和累计次数。',
        cardputer:'按机身的 G0 键，或聚焦模型后按 F12，观察屏幕计数和标记变化。',
        'atoms3-lite':'按住模型正面的按钮，RGB 指示灯变绿；松开后恢复蓝色。也可先点击模型，再按空格键。',
        'atom-lite':'按住模型正面的 USER 按钮，RGB 指示灯变绿；松开后恢复蓝色。也可先点击模型，再按空格键。',
        'atom-matrix':'按住模型正面的 USER 按钮，25 个 RGB 灯同时变绿；松开后恢复蓝色。当前示例仅验证同色输出，IMU 轴向待核验。',
        'atom-matrix-v11':'按住模型正面的 USER 按钮，25 个 RGB 灯同时变绿；松开后恢复蓝色。当前示例仅验证同色输出，IMU 轴向待核验。',
        'stickc':'按模型正面的 A 键，观察计数和屏幕标记变化；也可先点击模型，再按空格键。',
        'stickc-plus-se':'按模型正面的 A 键，观察计数和屏幕标记变化；也可先点击模型，再按空格键。',
        'stickc-plus2':'分别按模型上的 A、B 和电源键，观察各自的计数与屏幕变化。',
        papermono:'点击屏幕下方的触摸区域，观察计数和电子纸刷新；区域外点击不计数。',
        papercolor:'按模型正面的 A 键，观察计数和六色电子纸刷新。',
        stopwatch:'点击圆屏，观察计数和屏幕标记变化。'}[device.id]
      || '点击模型上的按键或触摸屏，观察设备屏幕中的计数变化。')
    : ref
    ? '已为当前设备选择对应固件。也可以使用自己的链接或本地文件。'
    : '请选择固件链接或本地 .bin 文件。';
}
function sourceChanged() {
  for (const [name, value] of [
    ['referenceFields', 'reference'],
    ['urlFields', 'url'],
    ['localFields', 'local'],
  ])
    $(name).hidden = source() !== value;
  updateFirmwareSelection();
  $('shareStatus').textContent = '';
  updateCapability();
}
function updateFirmwareSelection() {
  const selectedSource=source(), file=$('firmwareFile').files[0];
  $('firmwareSetup').dataset.firmwareSource=selectedSource;
  $('firmwareSetup').dataset.firmwareSelected=String(selectedSource==='local'&&!!file);
  $('localFileName').textContent=file?.name||'选择 .bin 固件';
  $('firmwareFileStatus').textContent=file?`已选择 ${bytes(file.size)}，启动时校验。`:'等待选择 .bin 固件';
}
function clearBrowserFrame() {
  $('rawFramePanel').hidden=true;
  const canvas=$('rawFrameCanvas');
  canvas.width=canvas.height=0;
  delete canvas.dataset.frameSequence;
  $('deviceMount').classList.remove('has-raw-frame');
  delete $('deviceMount').dataset.frameSequence;
  state.shell?.display?.fill('#000000');
  state.shell?.viewer?.requestRender();
}
function view(mode) {
  state.shell?.setViewMode?.(mode);
  for (const button of document.querySelectorAll('[data-view]'))
    button.setAttribute('aria-pressed', String(button.dataset.view === mode));
}
function normalizeDevice(device) {
  return {
    ...device,
    hardware: device.hardware || {display: device.display, soc: device.group_label || 'M5Stack', controls: []},
    shell: {
      ...(typeof device.shell === 'object' ? device.shell : {preset: 'core'}),
      ...(device.shell?.reference_image ? {reference_image: assetUrl(device.shell.reference_image, root)} : {}),
    },
  };
}
async function selectDevice(id, {openGeneration} = {}) {
  if(openGeneration===undefined)state.openGeneration++;
  else if(openGeneration!==state.openGeneration)return;
  const selection = ++state.selection,
    row = state.devices.find((d) => d.id === id);
  if (!row) return;
  await stopRun();
  if (selection !== state.selection) return;
  message('errorBanner');
  if(state.selected?.id!==row.id) {
    state.lastBrowserController=null;
    updateBrowserEvidence();
  }
  state.inventory = state.localUnitInventory;
  await state.picker?.attachShell(null);
  if(selection!==state.selection)return;
  await state.picker?.setDevice(id);
  if(selection!==state.selection)return;
  if(state.selected?.id!==row.id){$('firmwareSha').value='';$('cloudIdentityMac').value='';}
  state.referenceExplicit=false;
  $('referenceExample').value='uiflow';
  state.selected = row;
  updateReferenceDefault();
  renderDevices();
  $('stageTitle').textContent = row.name;
  $('stageSub').textContent = `${row.sku || ''} · ${row.hardware?.soc || row.group_label || 'M5STACK DEVICE'}`;
  state.shell?.dispose();
  state.shell = null;
  $('deviceMount').replaceChildren(node('p', 'stage-loading', '正在准备设备模型…'));
  clearBrowserFrame();
  updateBrowserBoot(null);
  updateFirmwareIdentity(null);
  const device = row.path
    ? {...row, ...(await json(assetUrl(`devices/${row.path}/device.json`))), browser: row.browser}
    : row;
  if (selection !== state.selection) return;
  state.selected = normalizeDevice(device);
  renderDetails();
  sourceChanged();
  updateCapability();
  const mount = node('div', 'device-render-mount');
  let shell;
  try {
    shell = row.visual_only
      ? await createVisualModelShell(mount, id)
      : await createDeviceShell(mount, state.selected, {live: true});
  } catch (cause) {
    if (selection === state.selection) {
      message('errorBanner', `设备模型加载失败：${cause.message}。可重新选择型号后重试。`);
      $('deviceMount').replaceChildren(node('p', 'stage-loading', '模型暂时不可用'));
    }
    return;
  }
  if (selection !== state.selection) {
    shell.dispose();
    return;
  }
  state.shell = shell;
  await state.picker?.attachShell(shell);
  if(selection!==state.selection){shell.dispose();return;}
  $('deviceMount').replaceChildren(mount);
  shell.viewer?.resize();
  shell.resetView?.();
  view('shell');
  document.querySelector('[data-view="shell"]').textContent = shell.model ? '3D' : '屏幕';
  $('resetViewBtn').disabled = !shell.model;
  const photo = !!state.selected.shell?.reference_image;
  document.querySelector('[data-view="photo"]').disabled = !photo;
  shell.on?.(
    'control',
    (event) => void deliverInput({type: 'button', id: event.key || event.id, down: event.down}, event),
  );
  shell.on?.(
    'touch',
    (event) =>
      void deliverInput(
        {type: 'touch', x: event.x, y: event.y, down: event.down ?? !['end', 'cancel'].includes(event.action)},
        event,
      ),
  );
  shell.on?.('encoder', event => void deliverEncoderInput(event));
  shell.on?.('reset', event => void deliverInput({type:'reset', down:true}, event));
  shell.on?.('capacitive-touch', event => void deliverInput({type:'capacitive-touch', zone:event.zone, down:event.down}, event));
  shell.on?.('unit-input', event => {
    const run=state.run;
    if(active(run)&&run.kind==='service'&&!state.busy)void run.controller.unitPanel?.handleInput(event);
  });
  status(
    'model',
    browserProfile(id) ? '选择固件后即可开始' : row.visual_only ? '此型号目前仅有视觉模型' : '尚未运行固件',
  );
  $('deviceMount').dataset.deviceId = id;
  if (matchMedia('(max-width: 800px)').matches) $('deviceLibrary').open = false;
  updateCapability();
  renderUnits();
  if (state.service) await loadServiceUnits(selection);
}
async function releaseInputs(run = state.run) {
  const held = [...state.holds.values()];
  state.holds.clear();
  await Promise.allSettled(held.map((command) => run?.controller.input({...command, down: false})));
}
async function deliverInput(command, original = {}) {
  const run = state.run;
  if (!active(run) || state.busy) return;
  try {
    if (run.kind === 'browser') {
      if (command.type==='touch' && run.controller instanceof PublicQemuRuntime && !run.controller.profile?.inputs.touch) return;
      if (command.type === 'reset') await releaseInputs(run);
      if (command.type === 'capacitive-touch') {
        const key = `capacitive-touch-${command.zone}`;
        if (command.down) state.holds.set(key, command);
        else state.holds.delete(key);
      } else if (command.type === 'button') {
        if (command.down) state.holds.set(command.id, command);
        else state.holds.delete(command.id);
      } else if (command.type === 'touch') {
        if (command.down) state.holds.set('touch', command);
        else state.holds.delete('touch');
      }
      // Natural power-off may finish before the pointer's release arrives.
      // Drop that trailing release after clearing the held-input bookkeeping.
      if (command.down === false && ['stopped', 'error'].includes(run.controller.status)) return;
      await run.controller.input(command);
    } else if (command.type === 'reset')
      await run.controller.reset();
    else if (command.type === 'button')
      await run.controller.input({kind: 'key', key: command.id, action: command.down ? 'down' : 'up'});
    else if (command.type === 'touch' && command.down && (!original.action || original.action === 'start'))
      await run.controller.input({kind: 'touch', x: command.x, y: command.y});
  } catch (cause) {
    if (active(run)) error(cause);
  }
}
async function deliverEncoderInput(event) {
  const run = state.run;
  if (!active(run) || state.busy || run.kind !== 'browser' || !(run.controller instanceof PublicQemuRuntime)
    || !run.controller.profile?.inputs.encoder) return;
  try {
    const next = advanceQemuEncoderTarget(run.controller.profile,
      run.encoderGesture || {target:0, remainderDegrees:0}, event.deltaDegrees);
    // This is pointer intent only. Observed guest counts remain serial/frame
    // data from the original RotaryIRQ; acknowledgements never set a count.
    run.encoderGesture = next.state;
    if (next.command) await run.controller.input(next.command);
  } catch (cause) { if (active(run)) error(cause); }
}
async function stopRun() {
  if (state.stopping) return state.stopping;
  const generation = ++state.runGeneration;
  state.abort?.abort();
  state.abort = null;
  const run = state.run;
  if (!run) {
    setBrowserModelsPaused(false);
    state.busy = false;
    await state.picker?.setLocked(false);
    status('stopped', '保留最后显示帧');
    message('runProgress');
    updateCapability();
    return;
  }
  run.stopping = true;
  run.stopGeneration = generation;
  state.busy = true;
  status('stopping', '正在保留记录并停止当前会话…');
  updateCapability();
  const attempt = (async () => {
    try {
      await releaseInputs(run);
      const lastSession = run.controller.current;
      const result=await run.controller.stop();
      if (run.controller instanceof PublicQemuRuntime) {
        updateBrowserBoot(result);
        renderBrowserHistory();
      }
      if (state.run === run) state.run = null;
      state.stopUnconfirmed = false;
      await state.picker?.setLocked(false);
      await state.picker?.attachShell(state.shell);
      clearBrowserOutputs(run.controller.outputProfile || run.controller.profile);
      status('stopped', run.controller.profile?.display===null?'无屏设备已停止，末次输出保留在运行记录'
        :result?.boot?.firstFrameSequence===null?'未取得屏幕帧':'保留最后显示帧',
        run.kind === 'service' ? {...lastSession, ...result, state: 'stopped'} : null);
      message('runProgress');
    } catch (cause) {
      state.stopUnconfirmed = true;
      status('stop_pending', '当前会话仍保留，请重试停止');
      $('stopBtn').textContent = '重试停止';
      const failure = new Error(`停止结果未确认。请重试停止当前会话：${cause.message}`);
      error(failure);
      throw failure;
    } finally {
      setBrowserModelsPaused(false);
      state.busy = false;
      if (state.stopping === attempt) state.stopping = null;
      updateCapability();
    }
  })();
  state.stopping = attempt;
  return attempt;
}
async function firmware(signal, runGeneration) {
  const selectedSource = source(),
    ref = reference(),
    expected = normalizeFirmwareSha256(
      $('firmwareSha').value.trim() || (selectedSource === 'reference' ? ref?.sha256 : null),
    );
  if (selectedSource === 'reference' && ref?.composedWorkbench) {
    const result=await composeUIFlowWorkbenchFirmware({profile:browserProfile(state.selected.id),registry:state.workbenchProfiles,root,signal,
      onProgress:progress=>{if(runGeneration===state.runGeneration)message('runProgress',progress.phase==='compose'?'正在准备 UIFlow 编程环境…':'正在校验 UIFlow 固件…');}});
    if(expected&&expected!==result.sha256)throw new Error('UIFlow 固件 SHA-256 与预期不一致。');
    return {bytes:result.bytes,sha256:result.sha256,name:result.fileName,size:result.bytes.byteLength,provenance:result.provenance};
  }
  if (selectedSource === 'reference' && ref?.composedProbe) {
    const result=await composeQemuProbeFirmware({profile:browserProfile(state.selected.id),root,signal,onProgress:()=>message('runProgress','正在本地组合设备示例')});
    if(expected&&expected!==result.sha256)throw new Error('设备示例 SHA-256 与预期不一致。');
    return {...result,name:result.fileName||`${state.selected.id}-probe.bin`,size:result.bytes.byteLength};
  }
  if (selectedSource === 'reference' && ref?.composed) {
    const phases = {'load-composer':'加载本地固件组合器','download-base':'下载官方固件基底','verify-base':'校验官方固件','compose':'写入示例源码','verify-result':'校验最终 Flash'};
    const compose=ref.wallclockCandidate?composeWallclockDemoFirmware:composeDemoFirmware;
    const result = await compose({signal,onProgress:(p)=>message('runProgress',phases[p.phase]||'正在准备浏览器示例')});
    if (expected && expected !== result.sha256) throw new Error('示例 SHA-256 与预期不一致。');
    return {...result,name:result.fileName||'cores3-lvgl-pir.bin',size:result.bytes.byteLength};
  }
  if (selectedSource !== 'local') {
    const url = selectedSource === 'reference' ? ref?.url : $('firmwareUrl').value.trim();
    if (!url) throw new Error('请先选择一个固件文件或填写公开固件地址。');
    return downloadFirmware(url, {
      signal,
      expectedSha256: expected,
      maxBytes: state.config.max_firmware_bytes || DEFAULT_MAX_FIRMWARE_BYTES,
      onProgress: (p) => {
        if (runGeneration === state.runGeneration)
          message('runProgress', `正在下载固件 · ${bytes(p.received)}${p.total ? ` / ${bytes(p.total)}` : ''}`);
      },
    });
  }
  const file = $('firmwareFile').files[0];
  if (!file?.size) throw new Error('请先选择非空的 .bin 固件文件。');
  if (file.size > (state.config.max_firmware_bytes || DEFAULT_MAX_FIRMWARE_BYTES))
    throw new Error('固件文件超过 64 MiB 上限。');
  const buffer = await file.arrayBuffer();
  const sha256 = await sha256Buffer(buffer, {signal});
  if (signal.aborted) throw new DOMException('已取消加载', 'AbortError');
  if (expected && expected !== sha256) throw new Error('固件 SHA-256 与预期不一致，未加载固件。');
  return {bytes: buffer, name: file.name, size: file.size, sha256};
}
function clearBrowserOutputs(profile) {
  message('actuatorStatus');
  $('deviceMount').dataset.outputKnown='false';
  if (!profile?.outputs) return;
  const commands=profile.outputs.kind==='stackchan-scs-qom-v1'
    ? ['yaw','pitch'].map(target=>({type:'joint',target,known:false}))
    : [...(profile.outputs.ledTargets||[profile.outputs.ledTarget]).map(target=>({type:'led',target,known:false})),
      {type:'button-state',target:profile.outputs.buttonTarget,pressed:false}];
  state.shell?.applyVisualState?.(commands);
  $('deviceMount').dataset.outputKnown='false';
}
function applyBrowserDeviceState(value, run, profile = run.controller.profile) {
  if (!active(run)) return;
  const servo=profile.outputs?.kind==='stackchan-scs-qom-v1';
  let transitionMs=0;
  if(servo){
    // QOM updates are discrete present-position samples. Smooth only the 3D
    // exhibit between adjacent observations; labels and evidence stay raw.
    const now=performance.now(), previous=run.servoPresentation;
    if(previous&&value.packets>=previous.packets){
      const observedGap=now-previous.observedAt;
      if(observedGap>=40)transitionMs=Math.min(1200,Math.max(80,observedGap*.9));
    }
    run.servoPresentation={observedAt:now,packets:value.packets};
  }
  const commands=servo?qemuServoVisualCommands(profile,value,transitionMs)
    :qemuOnboardVisualCommands(profile,value);
  state.shell.applyVisualState(commands);
  state.shell.viewer?.requestRender();
  const mount=$('deviceMount');
  mount.dataset.outputKnown='true';
  mount.dataset.outputSource=run.kind==='service'?'native-service-qom-v1':'browser-qemu-qom';
  if (servo) {
    const [yaw,pitch]=commands;
    mount.dataset.servoYawTicks=String(value.servos[0].present_position);
    mount.dataset.servoPitchTicks=String(value.servos[1].present_position);
    mount.dataset.servoPowered=String(value.powered);
    mount.dataset.servoPackets=String(value.packets);
    const diagnostic=qemuServoDiagnostic(profile,value);
    $('actuatorStatus').dataset.code=diagnostic.code;
    message('actuatorStatus',diagnostic.message);
    mount.dataset.outputLabel=`舵机 · 左右 ${yaw.angleDeg.toFixed(1)}° · 抬头 ${pitch.angleDeg.toFixed(1)}°${value.powered?'':' · 未供电'}`;
    $('frameStatus').textContent=mount.dataset.outputLabel;
  } else {
    const color=Array.isArray(value.led_rgb)?value.led_rgb.every(color=>color===value.led_rgb[0])
      ?`25 灯 · RGB #${value.led_rgb[0].toString(16).padStart(6,'0').toUpperCase()}`:'25 灯 · 多色帧已读取，空间顺序待验证'
      :`RGB #${value.led_rgb.toString(16).padStart(6,'0').toUpperCase()}`;
    $('frameStatus').textContent = `${color} · RMT ${value.led_frames} 帧 · 按键${value.pressed?'按下':'松开'}`;
    mount.dataset.outputFrames=String(value.led_frames);
  }
}
function applyBrowserPresentation(value, run = state.run) {
  if (!active(run)) return;
  const display = value?.display || null;
  state.shell?.setDeviceRotation?.(display?.deviceRotationDeg || 0);
  const panel = $('rawFramePanel');
  if (display?.orientation === 'portrait') panel.dataset.orientation = 'portrait';
  else delete panel.dataset.orientation;
  // Orientation arrives through QMP independently of shared-frame updates.
  // Repaint retained real pixels when static glass needs a new presentation.
  const frame = run.controller instanceof PublicQemuRuntime ? run.controller.lastFrame : null;
  if (frame) {
    const portrait=display?.orientation==='portrait',canvas=$('rawFrameCanvas');
    if (canvas.width!==(portrait?frame.height:frame.width)||canvas.height!==(portrait?frame.width:frame.height))
      applyBrowserFrame(frame,run);
  }
}
function applyBrowserFrame(frame, run) {
  if (!active(run)) return;
  if (state.config.browser_runtime_engine==='qemu-wasm' || state.selected.id === 'stopwatch' && frame.width === 468 && frame.height === 466) {
    const canvas = $('rawFrameCanvas');
    const portrait = run.controller instanceof PublicQemuRuntime && run.controller.display?.orientation === 'portrait';
    canvas.width = portrait ? frame.height : frame.width;
    canvas.height = portrait ? frame.width : frame.height;
    const context = canvas.getContext('2d'),
      image = context.createImageData(frame.width, frame.height);
    for (let i = 0, p = 0; i < frame.pixels.length; i += 2, p += 4) {
      const value = frame.pixels[i] | (frame.pixels[i + 1] << 8);
      image.data[p] = (((value >> 11) & 31) * 255) / 31;
      image.data[p + 1] = (((value >> 5) & 63) * 255) / 63;
      image.data[p + 2] = ((value & 31) * 255) / 31;
      image.data[p + 3] = 255;
    }
    if (!portrait) context.putImageData(image, 0, 0);
    else {
      const rotated = context.createImageData(frame.height, frame.width);
      for (let y = 0; y < frame.height; y++) for (let x = 0; x < frame.width; x++) {
        const from = (y * frame.width + x) * 4;
        // Match the portrait device presentation: native glass top-left
        // rotates clockwise into the flat-screen view.
        const to = (x * frame.height + frame.height - 1 - y) * 4;
        rotated.data.set(image.data.subarray(from, from + 4), to);
      }
      context.putImageData(rotated, 0, 0);
    }
    const touch=!(run.controller instanceof PublicQemuRuntime)||run.controller.profile?.inputs.touch;
    $('rawFrameDescription').textContent = portrait
      ? `竖屏应用 · ${frame.height} × ${frame.width} · 设备视图已同步旋转`
      : `完整 ${frame.width} × ${frame.height} 固件帧 · ${touch?'支持触摸':'请使用设备按键'}`;
    if (state.selected.id === 'stopwatch' && !(run.controller instanceof PublicQemuRuntime)) {
      const first = $('rawFramePanel').hidden;
      $('rawFramePanel').hidden = false;
      $('deviceMount').classList.add('has-raw-frame');
      if (first) {
        state.shell?.viewer?.resize();
        state.shell?.resetView?.();
      }
      $('frameStatus').textContent = `原始屏幕帧 ${frame.width} × ${frame.height} · 帧 ${frame.sequence}`;
      canvas.dataset.frameSequence = frame.sequence;
      return;
    }
    canvas.dataset.frameSequence = frame.sequence;
  }
  let applied;
  if (state.shell.setFrameLE) applied = state.shell.setFrameLE(frame.pixels, frame.width, frame.height, frame.sequence);
  else {
    const be = frame.pixels.slice();
    for (let i = 0; i < be.length; i += 2) [be[i], be[i + 1]] = [be[i + 1], be[i]];
    applied = state.shell.setFrame(be, frame.width, frame.height, frame.sequence);
  }
  if (applied !== false) {
    $('frameStatus').textContent = `实际屏幕 · ${frame.width} × ${frame.height} · 帧 ${frame.sequence}${run.controller.profile?.outputs?.kind==='stackchan-scs-qom-v1'&&$('deviceMount').dataset.outputKnown==='true'?' · '+$('deviceMount').dataset.outputLabel:''}`;
    $('deviceMount').dataset.frameSequence = frame.sequence;
  } else error(new Error(`固件输出 ${frame.width} × ${frame.height} 与当前模型屏幕不匹配。`));
}
async function startRun() {
  if (state.busy) return;
  const selection = state.selection;
  await stopRun();
  if (selection !== state.selection) return;
  message('errorBanner');
  message('launchNotice');
  const assembly=state.picker?.snapshot?.();
  if(assembly?.valid===false){error(new Error(assembly.issues?.[0]?.message||'请先调整 Unit 连线。'));updateCapability();return;}
  const kind = lane();
  if (kind === 'model') {
    view('shell');
    status('model', '模型交互不执行固件');
    return;
  }
  if (!kind) {
    error(new Error('当前设备需要兼容运行时。请连接仿真服务，或选择支持浏览器运行的设备。'));
    $('serviceConnection').open = true;
    return;
  }
  const generation = ++state.runGeneration,
    abort = (state.abort = new AbortController());
  state.busy = true;
  await state.picker?.setLocked(true, '停止当前运行后可修改 Unit 连线。');
  if (kind === 'browser') setBrowserModelsPaused(true);
  clearBrowserFrame();
  updateBrowserBoot(null);
  updateFirmwareIdentity(null);
  state.lastBrowserController=null;
  state.serial = '';
  state.serialBytes = 0;
  $('serialOutput').textContent = '';
  $('serialCount').textContent = '0 B';
  $('serialChannel').disabled = true;
  const consoleOption = document.createElement('option');
  consoleOption.value = 'console'; consoleOption.textContent = '默认控制台';
  $('serialChannel').replaceChildren(consoleOption);
  delete $('serialChannel').dataset.channels;
  status('loading', '等待本次运行的屏幕帧');
  updateCapability();
  let run;
  try {
    const ref=reference(), nativeWorkbench=kind==='service'&&source()==='reference'&&ref?.nativeWorkbench;
    const nativeCloud=kind==='service'&&source()==='reference'&&ref?.nativeCloud;
    const uiflowStartup=nativeCloud?{mode:'cloud',reference_sha256:ref.sha256}:undefined;
    const identitySupported=nativeCloud&&serviceCloudIdentity();
    const identityMac=identitySupported?$('cloudIdentityMac').value.trim():'';
    const deviceIdentity=identitySupported?(identityMac?{mac:identityMac}:{key:`uiflow-cloud-${state.selected.id}`}):undefined;
    if((nativeWorkbench||nativeCloud)&&$('firmwareSha').value.trim())throw new Error('此启动环境使用服务绑定的 UIFlow 固件。请清空自定义 SHA-256，或选择链接／本地文件校验指定固件。');
    const loaded = nativeWorkbench||nativeCloud ? {name:ref.name,size:0} : await firmware(abort.signal, generation);
    if (generation !== state.runGeneration || selection !== state.selection) return;
    clearBrowserOutputs(browserProfile(state.selected.id));
    message('runProgress', nativeCloud ? '正在启动官方 UIFlow2，联网与配对进度请查看设备屏幕…' : nativeWorkbench ? '正在启动本地 MicroPython 并连接所选 Unit…' : `已校验 ${loaded.name} · ${bytes(loaded.size)}，正在启动…`);
    run = {kind, generation, controller: null,cloudStartup:!!nativeCloud};
    const callbacks = {
      onSerial: (text) => {
        if (active(run)) appendSerial(text);
      },
      onSerialView: view => {if (active(run)) showSerialView(view);},
      onError: (cause) => {
        if (active(run)) {
          if (kind === 'browser') setBrowserModelsPaused(false);
          error(cause);
          status('error', '请查看错误信息或串口输出');
        } else if (run.stopping && run.stopGeneration === state.runGeneration) error(cause);
      },
    };
    if (kind === 'browser') {
      const BrowserRuntime = state.config.browser_runtime_engine==='qemu-wasm' ? PublicQemuRuntime : PublicBrowserRuntime;
      run.controller = new BrowserRuntime({
        ...callbacks,
        root,profiles:state.qemuProfiles,workbenchProfiles:state.workbenchProfiles,allowCandidateProfiles:state.config.publication_eligible===false,
        onFrame: (frame) => applyBrowserFrame(frame, run),
        onDeviceState: (value) => applyBrowserDeviceState(value, run),
        onState: (value) => {
          if (active(run)) {
            applyBrowserPresentation(value);
            if(value.boot) {
              updateBrowserBoot(value);
              updateFirmwareIdentity(value.runtime);
            }
            status(value.status);
            if (value.status==='stopped'||value.status==='error') clearBrowserOutputs(run.controller.profile);
            if (['running', 'paused', 'error', 'stopped'].includes(value.status)) setBrowserModelsPaused(false);
          }
        },
      });
      if (run.controller instanceof PublicQemuRuntime) {
        state.lastBrowserController = run.controller;
        $('browserPir').checked = false;
        $('browserPirState').textContent = 'QOM: CLEAR';
      }
      state.run = run;
      state.shell?.focusInput?.();
      await run.controller.start({device: state.selected.id, firmware: loaded.bytes, signal: abort.signal});
    } else {
      const imported = nativeWorkbench||nativeCloud ? null : await state.service.importFirmware(
        new File([loaded.bytes], loaded.name, {type: 'application/octet-stream'}),
        state.selected.id,
        {signal: abort.signal},
      );
      if (generation !== state.runGeneration) return;
      const units = state.picker?.attachments(state.selected.id) || [];
      let outputProfile = null;
      if (state.selected.id === 'stackchan') {
        try {
          const registry = state.qemuProfiles || await loadQemuBrowserProfiles({root, signal: abort.signal});
          const board = registry.profiles.find(profile => profile.deviceId === 'stackchan');
          if (board?.outputs?.kind === 'stackchan-scs-qom-v1' && typeof imported?.sha256 === 'string' && /^[a-f0-9]{64}$/.test(imported.sha256)) outputProfile = {
            deviceId: board.deviceId, board: board.board, outputs: structuredClone(board.outputs), firmwareSHA256: imported.sha256,
          };
        } catch (cause) {
          if (abort.signal.aborted) throw cause;
        }
      }
      if (generation !== state.runGeneration) return;
      clearBrowserOutputs(outputProfile);
      if (state.selected.id === 'stackchan' && !outputProfile) message('actuatorStatus', '当前服务的舵机状态尚未绑定。');
      run.controller = new PublicSessionController({
        ...callbacks,
        service: state.service,
        shell: state.shell,
        outputProfile,
        onDeviceState: value => applyBrowserDeviceState(value, run, outputProfile),
        onOutputState: value => {
          if (!active(run) || value.status === 'available') return;
          clearBrowserOutputs(outputProfile);
          message('actuatorStatus', value.status === 'pending' ? '正在等候新的舵机状态。' : '暂未取得可验证的舵机状态，可重置会话后重试。');
        },
        unitContainer: $('runtimeUnitPanel'),
        onState: (value) => {
          if (active(run)) {
            run.python?.bindSession(value.session);
            if (['stopped', 'failed'].includes(value.status)) clearBrowserOutputs(outputProfile);
            status(value.status, value.frameReady ? '实际会话屏幕已更新' : '等待应用显示帧', value.session);
          }
        },
      });
      state.run = run;
      if(nativeWorkbench) {
        run.python=new PublicServiceProgram({service:state.service,controller:run.controller,
          onState:()=>{if(active(run))updatePythonControls();}});
        status('booting', '正在连接本地 MicroPython 编程环境');
        await run.python.start({deviceId:state.selected.id,units,signal:abort.signal});
      } else await run.controller.start({deviceId:state.selected.id,...(nativeCloud?{uiflowStartup,deviceIdentity}:{firmwareId:imported.firmware_id}),units,signal:abort.signal});
    }
    if (active(run)) message('runProgress', nativeCloud ? '已创建官方 UIFlow2 会话，启动和配对进度请查看设备屏幕。' : nativeWorkbench ? `已启动 ${loaded.name}` : `已加载 ${loaded.name} · ${bytes(loaded.size)}`);
  } catch (cause) {
    if (generation === state.runGeneration) {
      if (run?.controller && state.run === run) {
        try {
          await stopRun();
        } catch {
          return;
        } // The retained native session must be stopped before retrying.
      }
      error(cause);
      status(cause.name === 'AbortError' ? 'stopped' : 'error', '可修改固件或运行选项后重试');
      setBrowserModelsPaused(false);
      state.busy = false;
      if(!state.run)await state.picker?.setLocked(false);
      updateCapability();
    }
  } finally {
    if (generation === state.runGeneration) {
      setBrowserModelsPaused(false);
      state.busy = false;
      updateCapability();
    }
  }
}
function updateServiceLinks() {
  for (const link of document.querySelectorAll('[data-service-console]')) {
    if (state.service) {
      link.href = new URL(link.dataset.serviceConsole, state.service.url + '/').href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.title = '打开已连接服务的控制台';
    } else {
      link.href = '#serviceConnection';
      link.removeAttribute('target');
      link.removeAttribute('rel');
      link.title = '连接仿真服务后打开控制台';
    }
  }
}
async function connectService() {
  const generation = ++state.serviceGeneration;
  $('connectServiceBtn').disabled = true;
  message('serviceStatus', '正在连接…');
  try {
    const url = normalizeServiceUrl($('serviceUrl').value.trim()),
      service = new PublicDeviceService(url, {token: $('serviceToken').value});
    const result = await service.devices();
    if (generation !== state.serviceGeneration) return;
    if (
      !Array.isArray(result.devices) ||
      result.devices.some((device) => !device || typeof device.device_id !== 'string' || typeof device.creatable !== 'boolean') ||
      new Set(result.devices.map((device) => device.device_id)).size !== result.devices.length
    )
      throw new Error('服务返回的设备目录无效。');
    // Keep the current service and its selected Units until the candidate is
    // admitted. An owned native session (including an unresolved create) must
    // finish its stop/recovery before another service can replace that owner.
    // A pending firmware load also belongs to the previous service generation.
    if (state.stopUnconfirmed || state.busy || state.run?.kind === 'service') await stopRun();
    if (generation !== state.serviceGeneration) return;
    state.service = service;
    state.serviceDevices = result.devices;
    $('cloudIdentityMac').value='';
    updateReferenceDefault();
    $('serviceUrl').value = service.url;
    updateServiceLinks();
    message('serviceStatus', `仿真服务已连接 · ${state.serviceDevices.filter((d) => d.creatable).length} 个可运行设备；设备联网状态请查看屏幕。`);
    await loadServiceUnits(state.selection);
    renderDetails();
    updateCapability();
    renderDevices();
    void refreshServiceSessions();
  } catch (cause) {
    if (generation === state.serviceGeneration) {
      if (state.service) {
        $('serviceUrl').value = state.service.url;
        $('serviceToken').value = state.service.token;
      } else {
        state.serviceDevices = [];
        state.inventory = state.localUnitInventory;
        await state.picker?.updateInventory(state.localUnitInventory);
      }
      message('serviceStatus', `连接失败：${cause.message}${state.service ? '；已保留原服务连接与 Unit 配置。' : ''}`);
      updateServiceLinks();
      renderUnits();
      updateCapability();
    }
  } finally {
    if (generation === state.serviceGeneration) $('connectServiceBtn').disabled = false;
  }
}
async function loadServiceUnits(selection) {
  const service = state.service,
    deviceId = state.selected?.id;
  if (!service || !state.serviceDevices.some((d) => d.device_id === deviceId && d.creatable)) {
    state.inventory = state.localUnitInventory;
    await state.picker?.updateInventory(state.localUnitInventory);
    renderUnits();
    return;
  }
  try {
    const inventory = await service.units(deviceId);
    if (selection !== state.selection || service !== state.service) return;
    state.inventory = inventory;
    await state.picker?.updateInventory(inventory);
    renderUnits();
  } catch (cause) {
    if (selection === state.selection) message('serviceStatus', `服务已连接，Unit 目录读取失败：${cause.message}`);
  }
}
async function refreshServiceSessions() {
  const service=state.service, generation=++state.serviceSessionsGeneration;
  const current=()=>service===state.service&&generation===state.serviceSessionsGeneration;
  if(!service){$('serviceSessionList').replaceChildren();$('sessionsStatus').textContent='连接仿真服务后，可在这里查看已有会话。';return;}
  try {
    const result=await service.request('/api/v1/sessions');
    if(!current())return;
    const sessions=[...new Map((result.sessions||[]).map(session=>[session.session_id,session])).values()], rows=[];
    $('sessionsStatus').textContent=`${sessions.length} 个会话 · 打开已有会话不会重新创建设备。`;
    for(const session of sessions) {
      const row=node('div','workbench-session');
      row.append(node('strong','',state.devices.find(d=>d.id===session.device_id)?.name||session.device_id),
        node('small','',`${session.state} · ${session.session_id.slice(0,8)}`));
      if(['running','booting'].includes(session.state)) {
        const button=node('button','text-button','在工作台打开');button.type='button';
        button.addEventListener('click',()=>{if(service===state.service)void openServiceSession(session.session_id).catch(error);});row.append(button);
      }
      rows.push(row);
    }
    $('serviceSessionList').replaceChildren(...rows);
  } catch(cause){if(current())$('sessionsStatus').textContent=`会话读取失败：${cause.message}`;}
}
async function openServiceSession(id) {
  if(state.run?.kind==='service'&&state.run.controller.current?.session_id===id&&!state.run.stopping) {
    state.openGeneration++;
    $('deviceMount').scrollIntoView({block:'center'});return;
  }
  const service=state.service, openGeneration=++state.openGeneration, session=await service.session(id);
  const current=()=>service===state.service&&openGeneration===state.openGeneration;
  if(!current())return;
  if(!state.devices.some(d=>d.id===session.device_id))throw new Error('当前工作台尚无此设备模型。');
  await selectDevice(session.device_id,{openGeneration});
  if(!current()||state.selected?.id!==session.device_id)return;
  await state.picker?.attachShell(null);
  if(!current())return;
  const run={kind:'service',generation:++state.runGeneration,owned:false,cloudStartup:session.uiflow_startup?.mode==='cloud'};
  run.controller=new PublicSessionController({service,shell:state.shell,unitContainer:$('runtimeUnitPanel'),
    onSerial:text=>{if(active(run))appendSerial(text);},onSerialView:view=>{if(active(run))showSerialView(view);},onError:cause=>{if(active(run))error(cause);},
    onState:value=>{if(active(run)){run.python?.bindSession(value.session);status(value.status,value.frameReady?'实际会话屏幕已更新':'等待应用显示帧',value.session);}}});
  state.run=run;await state.picker?.setLocked(true,'当前显示已创建的会话，停止查看后可修改装配草稿。');
  if(!current()||!active(run))return;
  if(session.management_binding||session.program_transport==='uart-repl'){
    run.python=new PublicServiceProgram({service,controller:run.controller,onState:()=>{if(active(run))updatePythonControls();}});
    await run.python.attach(session);
  } else await run.controller.adoptSession(session,{owned:false});
  if(!current()||!active(run)){await run.controller.stop();return;}
  status(session.state,'已打开现有会话；停止查看不会结束原会话');
  $('stopBtn').textContent='停止查看';
  $('deviceMount').scrollIntoView({block:'center'});
}
function runnableUnit(id) {
  if(!state.service||!state.serviceDevices.some(d=>d.device_id===state.selected?.id&&d.creatable))return false;
  const unit = state.inventory?.units?.find((unit) => unit.id === id);
  return (
    ['implemented', 'validated'].includes(unit?.runtime?.status) && unit.runtime.hosts?.includes(state.selected?.id)
  );
}
function renderUnits() {
  const query = $('unitSearch').value.trim().toLowerCase(),
    filtered = state.units.filter(
      (unit) =>
        `${unit.name} ${unit.id} ${unit.sku || ''}`.toLowerCase().includes(query) &&
        (state.unitFilter !== 'runtime' || runnableUnit(unit.id)),
    );
  $('unitResults').textContent =
    `${filtered.length} 个匹配${state.unitFilter === 'runtime' && !state.service ? ' · 先连接服务以确认运行支持' : ''}`;
  $('unitList').replaceChildren();
  for (const unit of filtered) {
    const button = node('button', 'unit-choice');
    button.type = 'button';
    button.dataset.unitModel = unit.id;
    button.setAttribute('aria-pressed', String(state.selectedUnit === unit.id));
    button.append(
      node('strong', '', unit.name),
      node('small', '', `${unit.sku || unit.id} · ${runnableUnit(unit.id) ? '本机可运行' : '模型预览'}`),
    );
    button.addEventListener('click', () => void selectUnit(unit.id).catch(error));
    $('unitList').append(button);
  }
  if (!filtered.length)
    $('unitList').append(
      node(
        'p',
        'empty-list',
        state.unitFilter === 'runtime'
          ? '当前没有已确认可运行的 Unit。可以浏览全部模型，或连接兼容服务。'
          : '没有匹配的 Unit。试试型号或 SKU。',
      ),
    );
  renderSelectedUnit();
}
function renderSelectedUnit() {
  const unit = state.units.find(row => row.id === state.selectedUnit);
  if (!unit) return;
  $('unitTitle').textContent = unit.name;
  $('unitCapability').textContent = runnableUnit(unit.id) ? '当前服务支持此主机' : '运行能力待确认';
  $('addSelectedUnitBtn').disabled = !state.picker || !!state.run || state.busy;
  $('unitPreviewNote').textContent = `下方为独立目录模型，不连接运行中的设备。添加到 ${state.selected?.name || '所选设备'} 后可在上方主机模型中查看连线；运行能力以所选后端为准。`;
}
function setBrowserModelsPaused(paused) {
  state.browserModelsPaused = paused;
  for (const shell of [state.shell, state.unitShell]) {
    if (paused) shell?.pauseRendering?.();
    else shell?.resumeRendering?.();
  }
}
function disposeUnitPreview() {
  state.unitPreviewGeneration++;
  state.unitShell?.dispose();
  state.unitShell = null;
  $('unitModelMount').replaceChildren();
  delete $('unitModelMount').dataset.unitId;
}
async function selectUnit(id) {
  const unit = state.units.find((unit) => unit.id === id);
  if (!unit) return;
  disposeUnitPreview();
  const generation = state.unitPreviewGeneration;
  state.selectedUnit = id;
  renderUnits();
  $('unitDetailBody').replaceChildren();
  for (const text of [unit.sku, ...(unit.limitations || []), unit.nextAction].filter(Boolean))
    $('unitDetailBody').append(node('p', '', text));
  $('unitDetails').hidden = false;
  $('unitDetails').open = false;
  const mount = node('div', 'unit-render-mount');
  $('unitModelMount').replaceChildren(node('p', 'stage-loading', '正在准备 Unit 模型…'));
  let shell;
  try {
    shell = await createVisualModelShell(mount, id);
  } catch (cause) {
    if (generation !== state.unitPreviewGeneration) return;
    $('unitModelMount').replaceChildren(node('p', 'stage-loading', 'Unit 模型暂时不可用，请重新选择后重试。'));
    throw cause;
  }
  if (generation !== state.unitPreviewGeneration) {
    shell.dispose();
    return;
  }
  state.unitShell = shell;
  $('unitModelMount').replaceChildren(mount);
  $('unitModelMount').dataset.unitId = id;
  shell.viewer?.resize();
  shell.resetView?.();
  if (state.browserModelsPaused) shell.pauseRendering?.();
}
async function share() {
  try {
    const selectedSource = source(),
      ref = reference(),
      firmwareUrl =
        selectedSource === 'url' ? $('firmwareUrl').value.trim() : selectedSource === 'reference' ? ref?.url : null;
    const url = buildShareUrl(
      {
        deviceId: state.selected.id,
        firmware: firmwareUrl,
        sha256: $('firmwareSha').value.trim() || (selectedSource === 'reference'&&!ref?.nativeCloud ? ref?.sha256 : null),
        serviceUrl: $('serviceUrl').value.trim(),
        mode: $('runtimeMode').value,
        autostart: $('runtimeMode').value !== 'model'&&!(selectedSource==='reference'&&ref?.nativeCloud),
      },
      new URL(root),
    );
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      $('shareStatus').textContent =
        selectedSource === 'reference'&&ref?.nativeCloud
          ? '已复制设备链接。连接支持云端配对的服务后，可启动官方 UIFlow2。'
          : selectedSource === 'local'
          ? '已复制设备链接。本地文件需由对方重新选择。'
          : '已复制链接，打开即可加载对应设备与固件。';
    } else $('shareStatus').textContent = `分享链接：${url}`;
  } catch (cause) {
    error(cause);
  }
}
async function json(url, fallback) {
  const response = await fetch(url);
  if (!response.ok) {
    if (fallback !== undefined) return fallback;
    throw new Error(`站点资源读取失败（${response.status}）。`);
  }
  return response.json();
}
async function init() {
  for (const item of document.querySelectorAll('[data-site-link]')) item.href = assetUrl(item.dataset.siteLink, root);
  updateServiceLinks();
  for (const item of document.querySelectorAll('[data-asset]')) item.src = assetUrl(item.dataset.asset, root);
  const [catalog, visual, browser, config] = await Promise.all([
    json(assetUrl('devices/catalog.json')),
    json(assetUrl('platform/web/vendor/m5stack-models/catalog/products.json')),
    json(assetUrl('platform/web/browser-profiles.json'), {devices: []}),
    json(assetUrl('platform/web/site-config.json'), {}),
  ]);
  state.config = config;
  if (config.browser_runtime_engine === 'qemu-wasm') {
    try {
      [state.qemuProfiles,state.workbenchProfiles]=await Promise.all([loadQemuBrowserProfiles({root}),loadUIFlowWorkbenchProfiles({root})]);
      const isolation = await ensurePublicIsolation({root});
      if (isolation.reloading) return;
    } catch (cause) {
      state.browserUnavailable = true;
      error(new Error(`${cause.message} 仍可浏览模型或连接 HTTPS 仿真服务。`));
    }
    renderBrowserHistory();
  }
  const rows = new Map(catalog.devices.map((d) => [d.id, {...d}]));
  for (const model of visual.products.filter((m) => m.category === 'controller'))
    if (!rows.has(model.id))
      rows.set(model.id, {
        id: model.id,
        name: model.name,
        sku: model.sku,
        visual_only: true,
        display: model.display,
        hardware: {display: model.display, controls: []},
        shell: {preset: 'core'},
        runtime: {status: 'visual-only'},
      });
  for (const profile of browser.devices) {
    const native = rows.get(profile.id);
    // An experimental browser profile cannot overwrite a native device's
    // wiring, path, or admission. Its complete row can replace a preview.
    if (native && !native.visual_only) {
      rows.set(profile.id, {...native, browser:profile.browser});
    } else if (config.browser_runtime_engine === 'qemu-wasm' && native && browserProfile(profile.id)) {
      rows.set(profile.id, {...native, visual_only:false, browser:profile.browser,
        runtime:{status:'browser-runtime'}});
    } else {
      rows.set(profile.id, profile);
    }
  }
  state.devices = [...rows.values()];
  state.units = visual.products.filter((model) => model.category === 'unit');
  const [unitCatalog,hostPorts,runtimeProfiles]=await Promise.all([
    json(assetUrl('platform/units/catalog.json')),json(assetUrl('platform/units/host-ports.json')),
    json(assetUrl('platform/units/runtime-profiles.json'))]);
  state.localUnitInventory={units:unitCatalog.units.map(unit=>({...unit,runtime:runtimeProfiles.units[unit.id]||{}})),hosts:hostPorts.hosts};
  state.inventory=state.localUnitInventory;
  state.picker=await createPublicUnitAssembly($('unitAssemblyPanel'),{deviceId:'cores3',catalog:state.localUnitInventory,
    onChange:()=>updateCapability(),onError:error});
  $('deviceCount').textContent = state.devices.length;
  $('unitCount').textContent = `${state.units.length} 个 Unit 模型`;
  $('catalogChip').textContent = `${state.devices.length} DEVICES / ${state.units.length} UNITS`;
  let launch;
  const params = new URLSearchParams(location.search);
  if (!params.has('device')) params.set('device', config.browser_runtime_engine === 'qemu-wasm' ? 'cores3' : config.browser_board_execution ? 'stopwatch' : 'cores3');
  try {
    launch = parseLaunchConfig(params.toString(), state.devices);
  } catch (cause) {
    error(cause);
    launch = {device: null, warnings: [], mode: 'auto', serviceUrl: '', firmware: null};
  }
  $('runtimeMode').value = launch.mode;
  const configuredServiceUrl = launch.serviceUrl || config.service_url || '';
  $('serviceUrl').value = configuredServiceUrl;
  if(configuredServiceUrl&&new URL(configuredServiceUrl).origin===location.origin) {
    $('localObservatoryLink').hidden = false;
    try {$('serviceToken').value=sessionStorage.getItem('m5-service-token')||'';} catch {}
  }
  if (launch.firmware) {
    $('firmwareUrl').value = launch.firmware;
    document.querySelector('[name="firmwareSource"][value="url"]').checked = true;
  }
  if (launch.sha256) $('firmwareSha').value = launch.sha256;
  if (launch.warnings.length) message('launchNotice', launch.warnings.join(' '));
  renderDevices();
  renderUnits();
  if (launch.device) {
    await selectDevice(launch.device.id);
    if (launch.sha256===DEMO_FIRMWARE.firmwareSHA256) $('referenceExample').value='stock-div8';
    else if (launch.sha256===WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256) $('referenceExample').value='wallclock-candidate';
    else if(state.qemuProfiles?.profiles.some(row=>row.deviceId===launch.device.id&&row.fixture?.firmwareSHA256===launch.sha256))$('referenceExample').value='probe';
    if(launch.sha256)$('firmwareSha').value=launch.sha256;
    renderDetails();updateCapability();
  }
  else {
    $('stageTitle').textContent = '请选择设备';
    $('deviceMount').replaceChildren(node('p', 'stage-loading', '链接中的设备无法确认，请从设备列表选择。'));
  }
  if (
    configuredServiceUrl &&
    launch.device &&
    !['browser', 'model'].includes(launch.mode)
  )
    await connectService();
  const sharedReference = (reference()?.composed || reference()?.composedProbe || reference()?.composedWorkbench) && launch.sha256 === reference().sha256;
  if ((launch.firmware || sharedReference) && launch.autostart && launch.device) {
    if (lane()) await startRun();
    else message('launchNotice', '已读取链接中的设备与固件。此设备需要仿真服务，连接后点击开始运行。');
  }
}
function renderBrowserHistory() {
  const rows = browserQemuHistory();
  $('browserHistory').hidden = rows.length === 0;
  $('browserHistoryText').textContent = rows.map(row=>`${row.stopped_at} · ${row.receipt.deviceId||'cores3'} · ${row.receipt.firmwareSha256.slice(0,12)} · ${row.cleanup.gracefulExit ? '正常退出' : '已释放浏览器容器'}`).join('\n');
}
$('search').addEventListener('input', renderDevices);
$('unitSearch').addEventListener('input', renderUnits);
for (const button of document.querySelectorAll('[data-device-filter]'))
  button.addEventListener('click', () => {
    state.deviceFilter = button.dataset.deviceFilter;
    for (const b of document.querySelectorAll('[data-device-filter]'))
      b.setAttribute('aria-pressed', String(b === button));
    renderDevices();
  });
for (const button of document.querySelectorAll('[data-unit-filter]'))
  button.addEventListener('click', () => {
    state.unitFilter = button.dataset.unitFilter;
    for (const b of document.querySelectorAll('[data-unit-filter]'))
      b.setAttribute('aria-pressed', String(b === button));
    renderUnits();
  });
for (const input of document.querySelectorAll('[name="firmwareSource"]'))
  input.addEventListener('change', sourceChanged);
$('referenceExample').addEventListener('change', () => {
  state.referenceExplicit=true;
  $('firmwareSha').value='';
  $('shareStatus').textContent='';
  renderDetails();updateCapability();
});
for (const button of document.querySelectorAll('[data-view]'))
  button.addEventListener('click', () => view(button.dataset.view));
$('resetViewBtn').addEventListener('click', () => {
  state.shell?.resetView?.();
  if (!state.shell?.resetView) state.shell?.viewer?.fit();
});
$('startBtn').addEventListener('click', () => void startRun().catch(error));
$('stopBtn').addEventListener('click', () => void stopRun().catch(error));
$('cancelLoadBtn').addEventListener('click', () => void stopRun().catch(error));
$('runtimeMode').addEventListener('change', ()=>{updateReferenceDefault();renderDetails();updateCapability();updatePythonControls();});
$('refreshSessionsBtn').addEventListener('click',()=>void refreshServiceSessions());
$('addSelectedUnitBtn').addEventListener('click',async()=>{
  try {await state.picker?.addUnit(state.selectedUnit);$('unitAssemblyPanel').scrollIntoView({block:'center'});}
  catch(cause){error(cause);}
});
$('connectServiceBtn').addEventListener('click', () => void connectService());
for (const link of document.querySelectorAll('[data-service-console]'))
  link.addEventListener('click', (event) => {
    if (state.service) return;
    event.preventDefault();
    $('serviceConnection').open = true;
    message('serviceStatus', '设备会话与 WebBurner 是仿真服务控制台，请先连接你有权使用的服务。');
    $('serviceUrl').focus();
    $('serviceConnection').scrollIntoView({block: 'center'});
  });
$('openServiceBtn').addEventListener('click', () => {
  $('serviceConnection').open = true;
  $('serviceUrl').focus();
});
$('shareBtn').addEventListener('click', () => void share());
$('pauseBtn').addEventListener('click', async () => {
  const run = state.run;
  if (!active(run) || run.kind !== 'browser') return;
  try {
    await releaseInputs(run);
    await (run.controller.status === 'paused' ? run.controller.resume() : run.controller.pause());
  } catch (cause) {
    if (active(run)) error(cause);
  }
});
$('firmwareFile').addEventListener('change', updateFirmwareSelection);
$('pythonRunBtn').addEventListener('click',()=>void runPython());
$('pythonInterruptBtn').addEventListener('click',async()=>{
  const run=state.run;
  try{await run?.python?.interrupt();if(active(run))$('pythonStatus').textContent='正在中断…';}catch(cause){error(cause);}
});
$('pythonClearBtn').addEventListener('click',()=>{$('pythonOutput').textContent='';});
$('pythonFile').addEventListener('change',async()=>{
  const file=$('pythonFile').files[0];if(!file)return;
  try{
    if(file.size>65536)throw new Error('Python 文件超过 64 KiB。');
    if(!file.name.toLowerCase().endsWith('.py'))throw new Error('请导入 .py 源码文件。');
    $('pythonSource').value=await file.text();$('pythonSource').focus();
  }catch(cause){$('pythonStatus').textContent=cause.message;}
  $('pythonFile').value='';
});
$('pythonSource').addEventListener('keydown',event=>{
  event.stopPropagation();
  if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();if(!$('pythonRunBtn').disabled)void runPython();}
});
$('serialForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const run = state.run,
    text = $('serialInput').value;
  if (!active(run) || !text) return;
  if (run.kind !== 'browser') {
    error(new Error('当前服务未开放串口文本输入。'));
    return;
  }
  if(run.serialSending)return;
  let owner;
  const controller=run.controller,generation=controller.generation,sessionId=controller.sessionId,consoleEpoch=controller.consoleEpoch;
  try {
    if(run.python?.busy)throw new Error('代码运行期间请使用中断按钮。');
    run.serialSending=true;updatePythonControls();
    if(controller instanceof PublicQemuRuntime){
      owner=controller.acquireUart();
      const encoded=new TextEncoder().encode(text+'\r\n');
      for(let i=0;i<encoded.length;i+=1024){
        if(!active(run)||controller.generation!==generation||controller.sessionId!==sessionId||controller.consoleEpoch!==consoleEpoch)
          throw new DOMException('串口所属设备已改变。','AbortError');
        await controller.writeUart(encoded.subarray(i,i+1024),owner);
      }
    }else await controller.input({type: 'uart', text: text + '\n'});
    if (active(run)) $('serialInput').value = '';
  } catch (cause) {
    if(active(run))error(cause);
  } finally {
    if(owner)controller.releaseUart(owner);
    run.serialSending=false;if(active(run))updatePythonControls();
  }
});
$('browserPir').addEventListener('change', async (event) => {
  const run = state.run;
  if (!active(run) || !run.controller.profile?.inputs.pir) return;
  try { const receipt = await run.controller.input({type:'pir',motion:event.target.checked});
    $('browserPirState').textContent = receipt.result.motion ? 'QOM: MOTION' : 'QOM: CLEAR';
  } catch (cause) { error(cause); }
});
$('nativeScreenBtn').addEventListener('click',()=>{
  $('rawFramePanel').hidden=!$('rawFramePanel').hidden;
  $('nativeScreenBtn').textContent=$('rawFramePanel').hidden?'平面触屏':'收起平面触屏';
});
$('browserEvidenceBtn').addEventListener('click', () => {
  const controller = state.lastBrowserController;
  if (!controller?.receipt) return;
  let url;
  try {
    url=URL.createObjectURL(new Blob([JSON.stringify(controller.evidence(),null,2)],{type:'application/json'}));
    const link=document.createElement('a');
    link.href=url;
    link.download=`${controller.receipt.deviceId||'cores3'}-${controller.sessionId}.json`;
    link.click();
    browserEvidenceState('download-requested','已请求浏览器下载，请查看下载列表。');
  } catch {
    browserEvidenceState('download-error','无法生成运行记录下载，请重试。');
  } finally {
    if(url)setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
});
$('unitExplorer').addEventListener('toggle', () => {
  if (!$('unitExplorer').open) disposeUnitPreview();
  else if (!state.unitShell && state.units[0]) void selectUnit(state.selectedUnit || state.units[0].id).catch(error);
});
for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel'])
  $('rawFrameCanvas').addEventListener(type, (event) => {
    if (type === 'pointermove' && !event.buttons) return;
    const canvas = $('rawFrameCanvas'),
      rect = canvas.getBoundingClientRect();
    if (type === 'pointerdown') canvas.setPointerCapture(event.pointerId);
    const shownX = Math.max(0, Math.min(canvas.width - 1, Math.floor(((event.clientX - rect.left) * canvas.width) / rect.width)));
    const shownY = Math.max(0, Math.min(canvas.height - 1, Math.floor(((event.clientY - rect.top) * canvas.height) / rect.height)));
    const portrait = canvas.closest('#rawFramePanel')?.dataset.orientation === 'portrait';
    void deliverInput({
      type: 'touch',
      x: portrait ? shownY : shownX,
      y: portrait ? canvas.width - 1 - shownX : shownY,
      down: ['pointerdown', 'pointermove'].includes(type),
    });
  });
window.addEventListener('blur', () => void releaseInputs());
window.addEventListener('pagehide', () => {
  state.selection++;
  disposeUnitPreview();
  state.abort?.abort();
  state.run?.controller.stop();
  state.shell?.dispose();
  state.picker?.dispose();
});

$('serialChannel').addEventListener('change', () => {
  const run = state.run;
  if (run?.kind === 'service' && active(run)) {
    try {run.controller.selectSerialChannel($('serialChannel').value);} catch (cause) {error(cause);}
  }
});

void init().catch(error);
