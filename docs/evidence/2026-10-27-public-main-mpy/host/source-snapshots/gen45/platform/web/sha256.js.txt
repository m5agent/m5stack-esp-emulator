const ROUND_CONSTANTS = Uint32Array.from([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const INITIAL_STATE = Uint32Array.from([
  0x6a09e667,
  0xbb67ae85,
  0x3c6ef372,
  0xa54ff53a,
  0x510e527f,
  0x9b05688c,
  0x1f83d9ab,
  0x5be0cd19,
]);

function rotateRight(value, bits) {
  return (value >>> bits) | (value << (32 - bits));
}

export class Sha256 {
  constructor() {
    this.state = new Uint32Array(INITIAL_STATE);
    this.buffer = new Uint8Array(64);
    this.bufferLength = 0;
    this.bytesHashed = 0;
    this.schedule = new Uint32Array(64);
    this.finalized = false;
  }

  update(data) {
    if (this.finalized) throw new Error('SHA256 is already finalized');
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    this.bytesHashed += bytes.length;
    let offset = 0;
    if (this.bufferLength) {
      const needed = Math.min(64 - this.bufferLength, bytes.length);
      this.buffer.set(bytes.subarray(0, needed), this.bufferLength);
      this.bufferLength += needed;
      offset += needed;
      if (this.bufferLength === 64) {
        this.#processBlock(this.buffer, 0);
        this.bufferLength = 0;
      }
    }
    while (offset + 64 <= bytes.length) {
      this.#processBlock(bytes, offset);
      offset += 64;
    }
    if (offset < bytes.length) {
      this.buffer.set(bytes.subarray(offset), 0);
      this.bufferLength = bytes.length - offset;
    }
    return this;
  }

  digest() {
    if (this.finalized) throw new Error('SHA256 is already finalized');
    const bitLength = this.bytesHashed * 8;
    const highBits = Math.floor(bitLength / 0x100000000);
    const lowBits = bitLength >>> 0;
    const paddingLength = this.bufferLength < 56
      ? 56 - this.bufferLength
      : 120 - this.bufferLength;
    const padding = new Uint8Array(paddingLength + 8);
    padding[0] = 0x80;
    const view = new DataView(padding.buffer);
    view.setUint32(paddingLength, highBits, false);
    view.setUint32(paddingLength + 4, lowBits, false);
    this.update(padding);
    const digest = new Uint8Array(32);
    const output = new DataView(digest.buffer);
    this.state.forEach((value, index) => {
      output.setUint32(index * 4, value, false);
    });
    this.finalized = true;
    return digest;
  }

  hex() {
    return [...this.digest()]
      .map(value => value.toString(16).padStart(2, '0'))
      .join('');
  }

  #processBlock(bytes, offset) {
    const words = this.schedule;
    for (let index = 0; index < 16; index += 1) {
      const position = offset + index * 4;
      words[index] = (
        (bytes[position] << 24) |
        (bytes[position + 1] << 16) |
        (bytes[position + 2] << 8) |
        bytes[position + 3]
      ) >>> 0;
    }
    for (let index = 16; index < 64; index += 1) {
      const previous15 = words[index - 15];
      const previous2 = words[index - 2];
      const sigma0 = (
        rotateRight(previous15, 7) ^
        rotateRight(previous15, 18) ^
        (previous15 >>> 3)
      ) >>> 0;
      const sigma1 = (
        rotateRight(previous2, 17) ^
        rotateRight(previous2, 19) ^
        (previous2 >>> 10)
      ) >>> 0;
      words[index] = (
        words[index - 16] + sigma0 + words[index - 7] + sigma1
      ) >>> 0;
    }

    let a = this.state[0];
    let b = this.state[1];
    let c = this.state[2];
    let d = this.state[3];
    let e = this.state[4];
    let f = this.state[5];
    let g = this.state[6];
    let h = this.state[7];
    for (let index = 0; index < 64; index += 1) {
      const sum1 = (
        rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25)
      ) >>> 0;
      const choice = ((e & f) ^ (~e & g)) >>> 0;
      const temp1 = (
        h + sum1 + choice + ROUND_CONSTANTS[index] + words[index]
      ) >>> 0;
      const sum0 = (
        rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22)
      ) >>> 0;
      const majority = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temp2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    this.state[0] = (this.state[0] + a) >>> 0;
    this.state[1] = (this.state[1] + b) >>> 0;
    this.state[2] = (this.state[2] + c) >>> 0;
    this.state[3] = (this.state[3] + d) >>> 0;
    this.state[4] = (this.state[4] + e) >>> 0;
    this.state[5] = (this.state[5] + f) >>> 0;
    this.state[6] = (this.state[6] + g) >>> 0;
    this.state[7] = (this.state[7] + h) >>> 0;
  }
}

export function sha256Bytes(bytes) {
  return new Sha256().update(bytes).hex();
}

export async function sha256Blob(blob, options = {}) {
  const chunkSize = Math.max(1, Number(options.chunkSize) || 4 * 1024 * 1024);
  const onProgress = options.onProgress || (() => {});
  const hasher = new Sha256();
  onProgress({ processed: 0, total: blob.size, ratio: 0 });
  for (let offset = 0; offset < blob.size; offset += chunkSize) {
    const end = Math.min(blob.size, offset + chunkSize);
    const chunk = new Uint8Array(await blob.slice(offset, end).arrayBuffer());
    hasher.update(chunk);
    onProgress({
      processed: end,
      total: blob.size,
      ratio: blob.size ? end / blob.size : 1,
    });
  }
  return hasher.hex();
}
