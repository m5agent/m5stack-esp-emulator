import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {findPublicButtonPointerTarget} from './public_qemu_button_pointer.mjs';
import {runPublicStockGuest} from './public_qemu_stock_guest.mjs';

const factory = {
  url:'https://github.com/m5stack/M5Cardputer-UserDemo/releases/tag/V0.9',
  bytes:2988720,
  sha256:'5a80d85877ca82feb888d404fd0a22659f1f5049bbf6db7615bf9c5b722923cb',
  flashSha256:'edcc5a24609bc298e2b20732f44bf1a39e278cb104952cbd5692a4b20c8a56ef',
};
// RGB565 reference oracles from the unmodified factory application's recorded
// splash, launcher and Fn indicator. They are only readback expectations.
const splash='31499c7452ea61dcae2d7023fd329746b08acd4e14754811748cdfdb8c5668ff';
const launcher='a9a144d24756851933a668840b8cf993a7c353b8b76bd48e47558a545339ec21';
const fnHeld='a8ff0d49522dc113c373dfeb4ad2b5caa16797dc0d59aeb22a3a49f6f7e51226';
const factoryAppCount='installed apps num: 9';

await runPublicStockGuest({device:'cardputer',board:'m5cardputer',firmware:factory,
  testScript:'platform/tests/test_public_qemu_cardputer_k132_stock.mjs',
  async exercise({page,canvas,origin,waitFrame,report,output,timeout}) {
    const before=await waitFrame(splash);
    assert.deepEqual([before.width,before.height],[240,135]);
    await canvas.screenshot({path:resolve(output,'factory-splash.png')});
    await canvas.focus();
    await page.keyboard.down('a');
    let selected;
    try {
      selected=await waitFrame(launcher);
      await page.waitForFunction(marker=>stockGuestRuntime.serial.includes(marker),factoryAppCount,{timeout});
    } finally {
      await page.keyboard.up('a');
    }
    assert.ok(selected.sequence>before.sequence);
    await canvas.screenshot({path:resolve(output,'factory-launcher.png')});
    await canvas.scrollIntoViewIfNeeded();
    const pointer=await page.evaluate(findPublicButtonPointerTarget,
      {componentId:'key-Fn',origin,shellGlobal:'stockGuestShell'});
    assert.equal(pointer.observed_hit.component,'key-Fn');
    await page.mouse.move(pointer.clientX,pointer.clientY);
    await page.mouse.down();
    let held;
    try { held=await waitFrame(fnHeld); }
    finally { await page.mouse.up(); }
    const released=await waitFrame(launcher);
    assert.ok(held.sequence>selected.sequence && released.sequence>held.sequence);
    assert.ok([selected,held,released].every(frame=>frame.sessionId===before.sessionId));
    const inputs=await page.evaluate(()=>stockGuestRuntime.inputs.map(({id,down})=>({id,down})));
    assert.deepEqual(inputs,[{id:'a',down:true},{id:'a',down:false},{id:'menu',down:true},{id:'menu',down:false}]);
    report.interaction={frames:{splash:before,launcher:selected,fnHeld:held,fnReleased:released},inputs,
      fnPointerComponent:pointer.observed_hit.component, serialMarker:factoryAppCount};
  },
});
