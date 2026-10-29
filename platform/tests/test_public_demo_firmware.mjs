// Cross-file identity and API compatibility; no network, browser or guest.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {DEMO_FIRMWARE, WALLCLOCK_DEMO_FIRMWARE,
  composeDemoFirmware, composeWallclockDemoFirmware} from '../web/public-demo-firmware.js';

for (const [directory,demo] of [['cores3_lvgl_pir',DEMO_FIRMWARE],['cores3_lvgl_wallclock',WALLCLOCK_DEMO_FIRMWARE]]) {
  const contract=JSON.parse(await readFile(new URL(`../../tests/browser-qemu/${directory}/contract.json`,import.meta.url)));
  assert.equal(demo.fixture,contract.fixture);
  assert.equal(demo.firmwareSHA256,contract.identity.composed_firmware.sha256);
  assert.equal(demo.rawBaseSHA256,contract.identity.raw_base.sha256);
  assert.equal(demo.normalizedBaseSHA256,contract.identity.normalized_base.sha256);
}
assert.equal(DEMO_FIRMWARE.fixture,'cores3-wasm-lvgl-pir-v1');
assert.equal(DEMO_FIRMWARE.firmwareSHA256,'78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f');
assert.equal(WALLCLOCK_DEMO_FIRMWARE.clockDivisor,1);
assert.equal(WALLCLOCK_DEMO_FIRMWARE.schedulerCandidate,'sdk-python-single-schedule-v1');
assert.notEqual(WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256,DEMO_FIRMWARE.firmwareSHA256);
assert.notEqual(composeWallclockDemoFirmware,composeDemoFirmware);
for(const compose of [composeDemoFirmware,composeWallclockDemoFirmware]) {
  const controller=new AbortController();controller.abort();
  await assert.rejects(compose({signal:controller.signal}),error=>error.name==='AbortError');
}
console.log('Pinned stock/div8 and explicit wallclock-candidate APIs remain separate; no guest executed');
