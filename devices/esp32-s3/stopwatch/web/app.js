const $ = (id) => document.getElementById(id);
const cv = $('screen'), ctx = cv.getContext('2d'), img = ctx.createImageData(466, 466);
const logEl = $('log'); let worker, fwBuf, frames = 0;
const VER = '20261020b';
let fwName = '-';
const send = (m) => worker && worker.postMessage(m);
const uart = (s) => send({ type: 'uart', data: s + '\n' });
function log(s) { logEl.textContent = (logEl.textContent + s).slice(-60000); logEl.scrollTop = 1e9; }

function start(buf, name) {
  if (worker) { worker.onmessage = null; worker.terminate(); worker = null; }   // full teardown: new WASM instance + flash
  fwBuf = buf; frames = 0; window.__frames = 0; if (name) fwName = name;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 466, 466); $('dev').classList.remove('vib');   // clear old framebuffer image
  $('status').textContent = '启动中…（未连接显示）';
  showInfo(buf);
  worker = new Worker('emu-worker.js?v=' + VER, { type: 'module' });
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === 'uart') log(m.data.replace(/\r/g, ''));
    else if (m.type === 'started') $('status').textContent = '运行中';
    else if (m.type === 'shared') { $('status').textContent = '运行中 · 显示已连接'; setTimeout(pushAll, 300); }
    else if (m.type === 'frame') drawFrame(m);
    else if (m.type === 'audio') playPCM(m.pcm, m.rate);
    else if (m.type === 'state') { $('dev').classList.toggle('vib', m.vib > 0); if (m.vib > 0) window.__vibCount = (window.__vibCount || 0) + 1; }
  };
  worker.onerror = (e) => log('\n[worker error] ' + e.message + '\n');
  worker.postMessage({ type: 'init', firmware: buf.slice(0) });
}
async function showInfo(buf) {
  const el = $('fwinfo'); el.textContent = `固件: ${fwName} · ${buf.byteLength} 字节 · sha256 计算中…`;
  try { const h = new Uint8Array(await crypto.subtle.digest('SHA-256', buf));
    const hex = [...h].map((x) => x.toString(16).padStart(2, '0')).join('');
    if (fwBuf === buf) { el.textContent = `固件: ${fwName} · ${buf.byteLength} 字节 · sha256 ${hex.slice(0, 16)}…`; el.title = hex; window.__fwSha = hex; }
  } catch (e) { el.textContent = `固件: ${fwName} · ${buf.byteLength} 字节`; }
}
function drawFrame(m) {
  const p = m.px, d = img.data;
  for (let i = 0, j = 0; i < p.length; i += 2, j += 4) {
    const v = (p[i] << 8) | p[i + 1];            // LGFX sprite = big-endian RGB565
    d[j] = ((v >> 11) & 31) * 255 / 31; d[j + 1] = ((v >> 5) & 63) * 255 / 63; d[j + 2] = (v & 31) * 255 / 31; d[j + 3] = 255;
  }
  ctx.putImageData(img, 0, 0); frames++; window.__frames = frames;
}
// ---- buttons: KEYA=G2, KEYB=G1 (active low); PWR via M5PM1 model
function key(el, down) {
  el.classList.toggle('on', down);
  if (el.id === 'kA') send({ type: 'gpio', pin: 2, high: !down });
  if (el.id === 'kB') send({ type: 'gpio', pin: 1, high: !down });
  if (el.id === 'kP') uart('@pwr ' + (down ? 1 : 0));
}
for (const id of ['kA', 'kB', 'kP']) {
  const el = $(id);
  el.onpointerdown = (e) => { e.preventDefault(); el.setPointerCapture(e.pointerId); key(el, true); };
  el.onpointerup = el.onpointercancel = () => el.classList.contains('on') && key(el, false);
}
const keymap = { a: 'kA', b: 'kB', p: 'kP' };
addEventListener('keydown', (e) => { if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName) || e.repeat) return; const k = keymap[e.key.toLowerCase()]; if (k) key($(k), true); });
addEventListener('keyup', (e) => { if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return; const k = keymap[e.key.toLowerCase()]; if (k) key($(k), false); });
// ---- touch CST820
let tdown = false;
function tp(e, d) { const r = cv.getBoundingClientRect(); const x = Math.round((e.clientX - r.left) * 466 / r.width), y = Math.round((e.clientY - r.top) * 466 / r.height);
  if (e.shiftKey && d) { $('ax').value = ((233 - x) / 233).toFixed(2); $('ay').value = ((y - 233) / 233).toFixed(2); pushImu(); return; }
  uart(`@tp ${x} ${y} ${d ? 1 : 0}`); }
cv.onpointerdown = (e) => { tdown = true; cv.setPointerCapture(e.pointerId); tp(e, 1); };
cv.onpointermove = (e) => { if (tdown) tp(e, 1); };
cv.onpointerup = (e) => { tdown = false; tp(e, 0); };
// ---- IMU / battery / RTC
function pushImu() { for (const k of ['ax', 'ay', 'az', 'gz']) $(k + 'v').textContent = $(k).value;
  uart(`@imu ${$('ax').value} ${$('ay').value} ${$('az').value} 0 0 ${$('gz').value}`); }
for (const k of ['ax', 'ay', 'az', 'gz']) $(k).oninput = pushImu;
$('tiltdrag').onclick = () => { $('ax').value = 0; $('ay').value = 0; $('az').value = 1; $('gz').value = 0; pushImu(); };
function pushBat() { const p = +$('bat').value; $('batv').textContent = p + '%'; uart(`@bat ${p} ${Math.round(3300 + p * 9)} ${$('chg').checked ? 1 : 0} ${$('vbus').checked ? 1 : 0}`); }
$('bat').oninput = $('chg').onchange = $('vbus').onchange = pushBat;
const localEpoch = (d) => Math.floor(d.getTime() / 1000 - d.getTimezoneOffset() * 60);
$('rtcsync').onclick = () => uart('@rtc ' + localEpoch(new Date()));
$('rtcapply').onclick = () => $('rtcset').value && uart('@rtc ' + localEpoch(new Date($('rtcset').value)));
function pushAll() { pushImu(); pushBat(); $('rtcsync').onclick(); }
// ---- speaker (WebAudio)
let ac, playT = 0;
function audio() { if (!ac) ac = new AudioContext(); if (ac.state === 'suspended') ac.resume(); return ac; }
function playPCM(pcm, rate) {
  $('audst').textContent = `收到 ${pcm.length} 个采样 @${rate}Hz`; window.__audioSamples = (window.__audioSamples || 0) + pcm.length; for (const v of pcm) window.__audioPeak = Math.max(window.__audioPeak || 0, Math.abs(v));
  if (!$('spk').checked) return;
  const a = audio(), b = a.createBuffer(1, pcm.length, rate), ch = b.getChannelData(0);
  for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
  const s = a.createBufferSource(); s.buffer = b; s.connect(a.destination);
  playT = Math.max(playT, a.currentTime + 0.02); s.start(playT); playT += b.duration;
}
// ---- microphone -> 8 kHz int8 -> "@mic <hex>" lines on UART0
let micQ = [];
function feedMic(f32, rate) { const step = rate / 8000; for (let i = 0; i < f32.length; i += step) micQ.push(f32[Math.floor(i)]); }
setInterval(() => {
  while (micQ.length) { const n = micQ.splice(0, 200); let s = '@mic ';
    for (const v of n) { const q = Math.max(-128, Math.min(127, Math.round(v * 127))) & 255; s += q.toString(16).padStart(2, '0'); }
    uart(s); }
}, 25);
$('mic').onclick = async () => {
  const a = audio(); const st = await navigator.mediaDevices.getUserMedia({ audio: true });
  const src = a.createMediaStreamSource(st), sp = a.createScriptProcessor(2048, 1, 1);
  sp.onaudioprocess = (e) => feedMic(e.inputBuffer.getChannelData(0), a.sampleRate);
  src.connect(sp); sp.connect(a.createGain()); sp.connect(a.destination); $('mic').textContent = '🎤 麦克风已开启';
};
$('wav').onchange = async (e) => { const f = e.target.files[0]; if (!f) return; const a = audio();
  const b = await a.decodeAudioData(await f.arrayBuffer()); const d = b.getChannelData(0), r = b.sampleRate;
  for (let o = 0; o < d.length; o += r / 10) { const sl = d.slice(o, o + r / 10); setTimeout(() => feedMic(sl, r), o / r * 1000); } };
$('tone').onclick = window.__tone = (sec = 2) => { const r = 8000, d = new Float32Array(r * sec); for (let i = 0; i < d.length; i++) d[i] = 0.8 * Math.sin(2 * Math.PI * 440 * i / r);
  for (let o = 0; o < d.length; o += 800) { const sl = d.slice(o, o + 800); setTimeout(() => feedMic(sl, r), o / r * 1000); } };
// ---- misc
$('cmd').onkeydown = (e) => { if (e.key === 'Enter') { uart(e.target.value); e.target.value = ''; } };
$('reset').onclick = () => fwBuf && start(fwBuf);
$('pause').onclick = () => { const p = $('pause').textContent === '暂停'; send({ type: p ? 'pause' : 'resume' }); $('pause').textContent = p ? '继续' : '暂停'; };
$('fw').onchange = async (e) => e.target.files[0] && start(await e.target.files[0].arrayBuffer(), '本地: ' + e.target.files[0].name);
window.__key = (id, d) => key($(id), d);
function loadUrl(u) { $('status').textContent = '下载固件…'; logEl.textContent = '';
  return fetch(u + (u.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error(r.status + ' ' + u); return r.arrayBuffer(); }).then((b) => start(b, u.split('/').pop())).catch((e) => log('加载固件失败: ' + e)); }
const qfw = new URLSearchParams(location.search).get('fw');
if (qfw) { if (![...$('fwsel').options].some((o) => o.value === qfw)) $('fwsel').add(new Option(qfw, qfw)); $('fwsel').value = qfw; }
$('fwsel').onchange = () => $('fwsel').value ? loadUrl($('fwsel').value) : ($('status').textContent = '等待固件', log('请下载 UIFlow2 固件或选择本地 merged .bin'));
if ($('fwsel').value) loadUrl($('fwsel').value);
else { $('status').textContent = '等待固件'; log('请下载 UIFlow2 固件或选择本地 merged .bin'); }

// Stable automation surface used by the device gallery and future device center.
window.m5emu = {
  loadFirmware: (buf, name = 'local-firmware') => start(buf, name),
  loadFirmwareUrl: (url) => loadUrl(url),
  reset: () => fwBuf && start(fwBuf, fwName),
  pause: () => send({ type: 'pause' }),
  resume: () => send({ type: 'resume' }),
  press: (id, down) => window.__key(id, down),
  touch: (x, y, down) => uart(`@tp ${x} ${y} ${down ? 1 : 0}`),
  setImu: (ax, ay, az, gx = 0, gy = 0, gz = 0) => uart(`@imu ${ax} ${ay} ${az} ${gx} ${gy} ${gz}`),
  setBattery: (pct, mv, charging, vbus) => uart(`@bat ${pct} ${mv} ${charging ? 1 : 0} ${vbus ? 1 : 0}`),
  setRtc: (epoch) => uart(`@rtc ${epoch}`),
  uart: (text) => uart(text),
  getFrame: () => document.getElementById('screen').toDataURL('image/png'),
  getLog: () => document.getElementById('log').textContent,
  getState: () => ({ frames: window.__frames || 0, sha256: window.__fwSha || null, status: document.getElementById('status').textContent }),
  screenshot: () => document.getElementById('dev').toDataURL('image/png')
};
