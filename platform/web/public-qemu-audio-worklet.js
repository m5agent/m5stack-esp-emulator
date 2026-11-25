import {qemuAudioReader,qemuAudioRing} from './public-qemu-audio.js';

class QemuPcmPlayer extends AudioWorkletProcessor {
  constructor({processorOptions}) {
    super();
    this.read = qemuAudioReader(qemuAudioRing(processorOptions.ring));
  }
  process(_, outputs) {
    this.read(outputs[0][0]);
    return true;
  }
}

registerProcessor('qemu-pcm-player', QemuPcmPlayer);
