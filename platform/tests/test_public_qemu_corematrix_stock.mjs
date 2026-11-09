import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {findPublicButtonPointerTarget} from './public_qemu_button_pointer.mjs';
import {runPublicStockGuest} from './public_qemu_stock_guest.mjs';

const firmware = {
  version:'UIFlow2 v2.5.4',
  url:'https://m5burner-cdn.m5stack.com/community/1/2104482080746106881/2116030913772818433/bin/2116030913772818434.bin',
  bytes:16773120,
  sha256:'0bfbe5a4acb467d93a7ded2186a4f73adea37511869328b563c15ab73163a018',
  flashSha256:'5562f685a8f3ed07d04ec7d7f58fa4435be8438fbf135c6fd61ff6e906783c07',
};
const romSha256='ba93108d967771826a8ba024da8c7002cf3c2c4346d600246b2fa882d95b30ec';
const bootMarkers=['V2.5.4','WiFi initialized','SSID: Not Found',
  'M5Stack CoreMatrix with ESP32-C61HR8','>>> '];
// Recorded from the stock application's 36-pixel missing-SSID cross.
const stockCross='af95bab4e8c242863fe41f184dfb77b4ccee4cdc1f1ebf0b2521635c72425365';
const usbPayload='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'.repeat(6);
const edges=[
  {mask:0},
  {id:'a',down:true,mask:1},
  {id:'a',down:false,mask:0},
  {id:'b',down:true,mask:2},
  {id:'b',down:false,mask:0},
  {id:'c',down:true,mask:4},
  {id:'a',down:true,mask:5},
  {id:'c',down:false,mask:1},
  {id:'a',down:false,mask:0},
];

function rectangleWithButtons(mask) {
  const pixels=Buffer.alloc(16*16*2);
  for(let y=2;y<5;y++) for(let x=1;x<5;x++) pixels.writeUInt16LE(0xffff,(y*16+x)*2);
  for(let bit=0;bit<3;bit++) if(mask&(1<<bit)) pixels.writeUInt16LE(0xffff,(2*16+8+2*bit)*2);
  return createHash('sha256').update(pixels).digest('hex');
}

// Volatile user code runs over the stock firmware's normal USB raw REPL.
// Each observed guest button state paints its own pixels on the TM1680.
const program=`import M5, time
print('CM_BOARD', M5.getBoard(), M5.Lcd.width(), M5.Lcd.height())
print('CM_LONG', '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' * 6)
M5.Lcd.clear(0)
M5.Lcd.fillRect(1, 2, 4, 3, 0xffffff)
prior = -1
edge = 0
until = time.ticks_add(time.ticks_ms(), 120000)
while edge < 9 and time.ticks_diff(until, time.ticks_ms()) > 0:
    M5.update()
    mask = M5.BtnA.isPressed() | (M5.BtnB.isPressed() << 1) | (M5.BtnC.isPressed() << 2)
    if mask != prior:
        M5.Lcd.fillRect(8, 2, 5, 1, 0)
        for bit in range(3):
            if mask & (1 << bit):
                M5.Lcd.fillRect(8 + 2 * bit, 2, 1, 1, 0xffffff)
        print('CM_EDGE', edge, mask)
        prior = mask
        edge += 1
    time.sleep_ms(10)
assert edge == 9
print('CM_DONE')
`;

await runPublicStockGuest({device:'corematrix',board:'esp32c61,m5corematrix=on',
  firmware,testScript:'platform/tests/test_public_qemu_corematrix_stock.mjs',
  async exercise({page,canvas,origin,waitFrame,report,output,timeout}) {
    assert.equal(report.runtime.romSha256,romSha256);
    assert.equal(report.runtime.uiflowWorkbench,null,'stock image was replaced by a composed workbench image');
    assert.equal(report.runtime.sourceCommit,report.provenance.c61_runtime_source_commit);
    assert.ok(Object.values(report.provenance.c61_runtime_assets)
      .some(asset=>asset.sha256===report.runtime.wasmSha256));
    await page.waitForFunction(markers=>markers.every(marker=>stockGuestRuntime.serial.includes(marker)),
      bootMarkers,{timeout});
    const stock=await waitFrame(stockCross);
    assert.deepEqual([stock.width,stock.height,stock.texturePixelsCompared],[16,16,256]);
    await canvas.screenshot({path:resolve(output,'stock-missing-ssid.png')});
    await page.locator('#pythonSource').fill(program);
    await page.locator('#pythonRunBtn').click();
    const expectOutput=line=>page.waitForFunction(line=>document.querySelector('#pythonOutput')
      .textContent.replaceAll('\r','').split('\n').includes(line),line,{timeout});
    const boardMarker='CM_BOARD 152 16 16';
    await expectOutput(boardMarker);
    await expectOutput('CM_LONG '+usbPayload);
    await canvas.scrollIntoViewIfNeeded();
    const pointer=await page.evaluate(findPublicButtonPointerTarget,
      {componentId:'btnB',origin,shellGlobal:'stockGuestShell'});
    assert.equal(pointer.observed_hit.component,'btnB');
    await canvas.focus();
    const frames=[];
    const heldKeys=new Set();
    let pointerHeld=false;
    try {
      for(const [index,{id,down,mask}] of edges.entries()){
        if(id==='b') {
          if(down) {
            await page.mouse.move(pointer.clientX,pointer.clientY);
            await page.mouse.down();
          } else await page.mouse.up();
          pointerHeld=down;
        } else if(id) {
          if(down) {
            await page.keyboard.down(id);
            heldKeys.add(id);
          } else {
            await page.keyboard.up(id);
            heldKeys.delete(id);
          }
        }
        const marker=`CM_EDGE ${index} ${mask}`;
        await expectOutput(marker);
        const frame=await waitFrame(rectangleWithButtons(mask));
        assert.equal(frame.sessionId,stock.sessionId);
        assert.ok(frame.sequence>(frames.at(-1)?.frame.sequence??stock.sequence));
        frames.push({marker,litPixels:12+((mask&1)+((mask>>1)&1)+((mask>>2)&1)),frame});
        if(mask===0 && index===0)await canvas.screenshot({path:resolve(output,'usb-repl-rectangle.png')});
        if(mask===5)await canvas.screenshot({path:resolve(output,'keyboard-ac-held.png')});
      }
    } finally {
      if(pointerHeld)await page.mouse.up();
      for(const id of heldKeys)await page.keyboard.up(id);
    }
    await expectOutput('CM_DONE');
    await page.getByText('运行完成',{exact:true}).waitFor({timeout});
    const inputs=await page.evaluate(()=>stockGuestRuntime.inputs.map(({id,down})=>({id,down})));
    assert.deepEqual(inputs,edges.slice(1).map(({id,down})=>({id,down})));
    report.interaction={bootMarkers,stock:{...stock,litPixels:36},boardMarker,
      usbTX:{payloadBytes:usbPayload.length,payloadSha256:createHash('sha256').update(usbPayload).digest('hex')},
      pointerButton:pointer.observed_hit.component,frames,inputs};
  },
});
