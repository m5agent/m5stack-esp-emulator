import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createQemuAudioPlayer} from '../web/public-qemu-audio-player.js';
import {
  CORES3_MIC_FIRMWARE_SHA, CORES3_WAV_SHA, CORES3_WAV_SD_SHA, QEMU_AUDIO_FRAMES, QEMU_AUDIO_RATE,
  hasQemuAudioPatches, qemuAudioExample, qemuAudioReader, qemuAudioRing, qemuAudioStats, qemuVirtualMic,
  setQemuAudioActive, writeQemuAudio,
} from '../web/public-qemu-audio.js';
import {PublicQemuRuntime} from '../web/public-qemu-runtime.js';

const patches = ['0045-cores3-i2s-tx-descriptor-pacing.patch', '0046-cores3-i2s-web-pcm-stream.patch']
  .map(name => ({path:'patches/qemu-wasm-probe/' + name, sha256:'a'.repeat(64)}));
const wav = {deviceId:'cores3',inputSHA256:CORES3_WAV_SHA,firmwareSHA256:CORES3_WAV_SHA,
  sdSHA256:CORES3_WAV_SD_SHA,patches};
assert.equal(qemuAudioExample('wav', wav), 'wav');
assert.equal(qemuAudioExample('mic', {...wav,inputSHA256:CORES3_MIC_FIRMWARE_SHA,firmwareSHA256:CORES3_MIC_FIRMWARE_SHA}), 'mic');
for (const mismatch of [{deviceId:'cardputer-adv'},{inputSHA256:null},{firmwareSHA256:null},{sdSHA256:null},{patches:patches.slice(0,1)}]) {
  assert.equal(qemuAudioExample('wav', {...wav,...mismatch}), null);
}
assert.equal(qemuAudioExample('mic', wav), null);
assert.equal(qemuAudioExample(undefined, wav), null);
assert.equal(hasQemuAudioPatches([null,...patches.map(row=>({...row,sha256:'invalid'}))]), false);

const mic = qemuVirtualMic();
assert.equal(mic.byteLength, 32000);
assert.equal(createHash('sha256').update(mic).digest('hex'), '97baea0a56c5b48504ea4b65b41148c6d55dc494d22652b3db7cedb295876efe');
assert.deepEqual(qemuVirtualMic(), mic);

const ring = qemuAudioRing();
assert.equal(ring.samples.length, QEMU_AUDIO_FRAMES);
assert.throws(() => qemuAudioRing(new SharedArrayBuffer(9)), /layout mismatch/);
const read = qemuAudioReader(ring);
const output = new Float32Array(128);
const pcm = new Uint8Array((QEMU_AUDIO_FRAMES + 10) * 2);
for (let i = 0; i < pcm.length; i += 4) pcm.set([0x00,0x40,0x00,0xc0].slice(0, pcm.length-i), i);
setQemuAudioActive(ring, true);
read(output); // Observe this playback epoch before its first producer write.
assert.equal(writeQemuAudio(ring, pcm, 0, pcm.length), pcm.length);
read(output);
assert.deepEqual(Array.from(output.slice(0, 4)), [0.5,-0.5,0.5,-0.5]);
assert.deepEqual(qemuAudioStats(ring), {dropped:10,rendered:128,nonzero:128,starved:0});
for (let i = 0; i < 64; i++) read(output);
assert.equal(qemuAudioStats(ring).starved,128);
assert.ok(output.every(sample => sample === 0));
writeQemuAudio(ring, pcm, 0, 2048);
setQemuAudioActive(ring, false);
read(output);
assert.ok(output.every(sample => sample === 0));
setQemuAudioActive(ring, true);
read(output);
assert.ok(output.every(sample => sample === 0));

// Emscripten's WASI fd_write hands the FS callback a signed HEAP8 view.
const heap = new Int8Array(new SharedArrayBuffer(2052));
for (let i = 4; i < heap.length; i += 4) heap.set([0xc6,0x12,0xa5,0xbc],i);
writeQemuAudio(ring,heap,4,2048);
read(output);
assert.deepEqual(Array.from(output.slice(0,2)),[0x12c6/32768,(0xbca5-65536)/32768]);

const freshRing = qemuAudioRing();
const readFresh = qemuAudioReader(freshRing);
setQemuAudioActive(freshRing, true);
writeQemuAudio(ring, pcm, 0, 2048);
readFresh(output);
assert.ok(output.every(sample => sample === 0));

let resume, load, calls = [];
globalThis.AudioContext = class {
  constructor(options) {
    assert.equal(options.sampleRate,QEMU_AUDIO_RATE);
    this.sampleRate = options.sampleRate;
    this.destination = {};
    this.audioWorklet = {addModule(url) {
      assert.match(url.pathname,/public-qemu-audio-worklet\.js$/);
      calls.push('module');
      return new Promise(resolve => {load = resolve;});
    }};
  }
  resume() {
    calls.push('resume');
    return new Promise(resolve => {resume = resolve;});
  }
  close() {calls.push('closed');return Promise.resolve();}
};
globalThis.AudioWorkletNode = class {
  constructor(context, name, options) {
    assert.equal(name,'qemu-pcm-player');
    assert.ok(options.processorOptions.ring instanceof SharedArrayBuffer);
    this.destination = context.destination;
  }
  connect(destination) {assert.equal(destination,this.destination);calls.push('connect');}
  disconnect() {calls.push('disconnect');}
};

const early = createQemuAudioPlayer();
assert.deepEqual(calls,['resume']);
const loading = early.connect();
resume();
await Promise.resolve();
early.close();
load();
assert.equal(await loading,false);
assert.deepEqual(calls,['resume','module','closed']);

calls = [];
const player = createQemuAudioPlayer();
const connecting = player.connect();
resume();
await Promise.resolve();
load();
assert.equal(await connecting,true);
const runtime = new PublicQemuRuntime();
runtime.audioPlayer=player;
runtime.receipt={audio:{example:'wav'}};
runtime.state('running');
const shared=qemuAudioRing(player.ring);
const readPlayer=qemuAudioReader(shared);
writeQemuAudio(shared,pcm,0,2048);
readPlayer(output);
assert.ok(output.some(sample=>sample!==0));
runtime.state('paused');
readPlayer(output);
assert.ok(output.every(sample=>sample===0));
runtime.state('running');
readPlayer(output);
assert.ok(output.every(sample=>sample===0));
await runtime.stop();
assert.deepEqual(runtime.receipt.audio.stats,{dropped:0,rendered:128,nonzero:128,starved:0});
assert.equal(runtime.audioPlayer,null);
player.close();
assert.deepEqual(calls,['resume','module','connect','disconnect','closed']);
console.log('CoreS3 audio admission, fixed virtual input, ring and player generation contracts passed');
