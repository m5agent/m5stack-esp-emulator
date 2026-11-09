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
// Check the launcher apps and modifier indicators below the live clock and
// battery bar. Their stable regions do not depend on RTC or ADC calibration.
const launcherRegion=[0,24,240,111];
const launcher='2f54f832b9db9314e3c0f299be729d4ca6361316a71897b41ae771d50fe6e593';
const fnHeld='11eb5888918170719c4553aa28729f6b9ae5ee87a120ae2d92589d5224600d98';
const factoryAppCount='installed apps num: 9';
const uiflow = {
  url:'https://m5burner-cdn.m5stack.com/community/1/1897200000000000718/2116030814376202242/bin/2116030814376202243.bin',
  bytes:8384512,
  sha256:'d9e1287eccb641863e7b1cc7cf057733592403d65aeec2d4b1fa4cb3e8b1b309',
  flashSha256:'d06401203f048d7ac150ab90e2256c12934b2b87c330fc9a6c0e91979ac0e9ae',
};
const selectedCase=process.env.M5_CARDPUTER_STOCK_CASE || 'factory-v09';
assert.ok(['factory-v09','uiflow2-v254'].includes(selectedCase),'Unknown K132 stock firmware case');

await runPublicStockGuest({device:'cardputer',board:'m5cardputer',
  firmware:selectedCase==='factory-v09'?factory:uiflow,
  testScript:'platform/tests/test_public_qemu_cardputer_k132_stock.mjs',
  async exercise({page,canvas,origin,waitFrame,report,output,timeout}) {
    if(selectedCase==='uiflow2-v254'){
      const offline=await waitFrame('928b23eb10887120636d16607c6a53beb8e825b52c592b0a8a4ee6e7d0838f53',[3,19,140,22]);
      await canvas.screenshot({path:resolve(output,'uiflow2-offline.png')});
      await canvas.focus();
      await page.keyboard.down('F12');
      try { await page.waitForTimeout(250); }
      finally { await page.keyboard.up('F12'); }
      const menu=await waitFrame('d5b1ef94770e44151fb894e9dd19f40e910b06da15e7a2736174560d7f7099e9',[87,35,66,66]);
      assert.equal(menu.sessionId,offline.sessionId);
      assert.ok(menu.sequence>offline.sequence);
      const inputs=await page.evaluate(()=>stockGuestRuntime.inputs.map(({id,down})=>({id,down})));
      assert.deepEqual(inputs,[{id:'f12',down:true},{id:'f12',down:false}]);
      report.interaction={frames:{offline,menu},inputs,holdMilliseconds:250,
        regions:{offlineBadge:[3,19,140,22],developTile:[87,35,66,66]}};
      await canvas.screenshot({path:resolve(output,'uiflow2-develop-menu.png')});
      return;
    }
    const before=await waitFrame(splash);
    assert.deepEqual([before.width,before.height],[240,135]);
    await canvas.screenshot({path:resolve(output,'factory-splash.png')});
    await canvas.focus();
    // V0.9 Launcher::_port_wait_enter() waits for key release before drawing
    // the menu. Hold one bounded real PC key press across its polling loop.
    await page.keyboard.down('a');
    try { await page.waitForTimeout(500); }
    finally { await page.keyboard.up('a'); }
    const selected=await waitFrame(launcher,launcherRegion);
    await page.waitForFunction(marker=>stockGuestRuntime.serial.includes(marker),factoryAppCount,{timeout});
    assert.ok(selected.sequence>before.sequence);
    await canvas.screenshot({path:resolve(output,'factory-launcher.png')});
    await canvas.scrollIntoViewIfNeeded();
    const pointer=await page.evaluate(findPublicButtonPointerTarget,
      {componentId:'key-Fn',origin,shellGlobal:'stockGuestShell'});
    assert.equal(pointer.observed_hit.component,'key-Fn');
    await page.mouse.move(pointer.clientX,pointer.clientY);
    await page.mouse.down();
    let held;
    try { held=await waitFrame(fnHeld,launcherRegion); }
    finally { await page.mouse.up(); }
    const released=await waitFrame(launcher,launcherRegion);
    assert.ok(held.sequence>selected.sequence && released.sequence>held.sequence);
    assert.ok([selected,held,released].every(frame=>frame.sessionId===before.sessionId));
    const inputs=await page.evaluate(()=>stockGuestRuntime.inputs.map(({id,down})=>({id,down})));
    assert.deepEqual(inputs,[{id:'a',down:true},{id:'a',down:false},{id:'menu',down:true},{id:'menu',down:false}]);
    report.interaction={frames:{splash:before,launcher:selected,fnHeld:held,fnReleased:released},inputs,
      launcherRegion,launcherKeyHoldMilliseconds:500,fnPointerComponent:pointer.observed_hit.component,serialMarker:factoryAppCount};
  },
});
