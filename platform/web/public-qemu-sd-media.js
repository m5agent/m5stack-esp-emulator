import {assetUrl} from './public-config.js';
import {DEFAULT_MAX_FIRMWARE_BYTES,sha256Buffer} from './public-firmware.js';

const SHA256 = /^[a-f0-9]{64}$/;
const SD_BOARDS = new Set(['cores3', 'cardputer-adv']);

function check(value) {
  if (!value) throw new Error('示例 microSD 镜像的配置、长度或 SHA-256 无效。');
}

export function validQemuSdImage(device, bytes) {
  return SD_BOARDS.has(device) && Number.isSafeInteger(bytes)
    && bytes > 0 && bytes <= DEFAULT_MAX_FIRMWARE_BYTES && bytes % 512 === 0;
}

export async function loadQemuSdExample(examples, device, firmwareSha256, {root, signal, loadAsset, fetchImpl}) {
  check(Array.isArray(examples));
  const matches = examples.filter(row => row?.device === device && row.firmware_sha256 === firmwareSha256);
  if (!matches.length) return null;
  check(matches.length === 1);
  const {bytes, sha256, gzip_bytes: gzipBytes, gzip_sha256: gzipSha256} = matches[0];
  check(validQemuSdImage(device, bytes) && typeof sha256 === 'string' && SHA256.test(sha256)
    && typeof gzipSha256 === 'string' && SHA256.test(gzipSha256)
    && Number.isSafeInteger(gzipBytes) && gzipBytes > 0 && gzipBytes <= DEFAULT_MAX_FIRMWARE_BYTES);
  signal.throwIfAborted();
  const url = assetUrl(`platform/runtime/qemu/sd-media/${sha256}.img.gz`, root);
  const {bytes: compressed} = await loadAsset(url, {
    signal, expectedBytes: gzipBytes, expectedSha256: gzipSha256, maxBytes: gzipBytes,
    fetchImpl: (url, options) => fetchImpl(url, {...options, redirect: 'error'}),
  });
  signal.throwIfAborted();

  // Only the gzip seed is cached. Each engine gets an independent writable image.
  const image = new Uint8Array(bytes);
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const reader = stream.getReader();
  let offset = 0;
  try {
    for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
      signal.throwIfAborted();
      check(chunk.value.byteLength <= bytes - offset);
      image.set(chunk.value, offset);
      offset += chunk.value.byteLength;
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  signal.throwIfAborted();
  check(offset === bytes && await sha256Buffer(image, {signal}) === sha256);
  return {image: image.buffer, identity: {sha256, bytes, mode: 'session-copy'}};
}
