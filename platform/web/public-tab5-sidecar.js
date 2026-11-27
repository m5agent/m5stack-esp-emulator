import { sha256Bytes } from './sha256.js';

// ESP-Hosted 2.0.13, as pinned in scripts/esp32sim-runtime.lock.json.
export const TAB5_SIDECAR_URL = 'https://github.com/m5agent/esp32sim/releases/download/m5-device-service-20261127/tab5-esp-hosted-2.0.13-c6.zip';
const archiveSHA256 = '73fba21169b8a518b7cc9f46681446f8a1e1b769a9084301d7501a2347b487c2';
const files = new Map([
  ['bootloader/bootloader.bin', [0,23760,'f15f13d257f14c8c132a116bb65a52ab5c149082d0d53c92684850129008e425']],
  ['partition_table/partition-table.bin', [0x8000,3072,'0241fa0d2e573dee86756e39fb4181e61ff7218087619cab565b602df55954d6']],
  ['ota_data_initial.bin', [0xd000,8192,'7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f']],
  ['network_adapter.bin', [0x10000,852688,'33d0e47ad5b8802e4f3c0c2feed5a7445e2553b5789b3770153e55fbe2f90a8b']],
]);

export async function readTab5Sidecar(archive) {
  if (!(archive instanceof ArrayBuffer) || archive.byteLength !== 520312
      || sha256Bytes(new Uint8Array(archive)) !== archiveSHA256)
    throw new Error('请选择已校验的 Tab5 ESP-Hosted 2.0.13 C6 ZIP 文件。');
  // Parse local headers only after verifying the entire fixed archive. No
  // member names are used as filesystem paths, and only four members inflate.
  const data = new DataView(archive), decoder = new TextDecoder();
  const flash = new Uint8Array(4 * 1024 * 1024).fill(0xff), read = new Set();
  for (let start = 0; start + 30 <= data.byteLength && data.getUint32(start,true) === 0x04034b50;) {
    const flags = data.getUint16(start+6,true), method = data.getUint16(start+8,true);
    const length = data.getUint32(start+18,true), size = data.getUint32(start+22,true);
    const nameLength = data.getUint16(start+26,true), extraLength = data.getUint16(start+28,true);
    const offset = start + 30 + nameLength + extraLength, end = offset + length;
    if (flags !== 0 || method !== 8 || end > data.byteLength) throw new Error('Tab5 C6 ZIP 格式无效。');
    const name = decoder.decode(new Uint8Array(archive,start+30,nameLength));
    const entry = files.get(name);
    if (entry) {
      const [address,expectedSize,expectedHash] = entry;
      if (read.has(name) || size !== expectedSize) throw new Error('Tab5 C6 ZIP 文件清单不匹配。');
      const stream = new Blob([archive.slice(offset,end)]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
      if (bytes.length !== expectedSize || sha256Bytes(bytes) !== expectedHash) throw new Error('Tab5 C6 固件校验失败。');
      flash.set(bytes,address);
      read.add(name);
    }
    start = end;
  }
  if (read.size !== files.size) throw new Error('Tab5 C6 ZIP 缺少固件段。');
  return {flash:flash.buffer,archiveSHA256,flashSHA256:sha256Bytes(flash)};
}
