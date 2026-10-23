import assert from 'node:assert/strict';
import { createHash, randomBytes } from 'node:crypto';
import { sha256Blob, sha256Bytes } from '../web/sha256.js';

const vectors = [
  ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
  ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
  [
    'The quick brown fox jumps over the lazy dog',
    'd7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592',
  ],
];

for (const [value, expected] of vectors) {
  assert.equal(sha256Bytes(new TextEncoder().encode(value)), expected);
}

const random = randomBytes(1024 * 1024 + 37);
const expected = createHash('sha256').update(random).digest('hex');
assert.equal(sha256Bytes(random), expected);
assert.equal(
  await sha256Blob(new Blob([random]), { chunkSize: 65537 }),
  expected,
);

const progress = [];
await sha256Blob(new Blob([random.subarray(0, 131071)]), {
  chunkSize: 32768,
  onProgress: event => progress.push(event.processed),
});
assert.deepEqual(progress, [0, 32768, 65536, 98304, 131071]);

console.log('SHA256_OK');
