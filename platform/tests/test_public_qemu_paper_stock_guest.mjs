import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {runPublicStockGuest} from './public_qemu_stock_guest.mjs';

const device=process.env.M5_QEMU_DEVICE;
assert.ok(['papers3','paperdiy'].includes(device),'M5_QEMU_DEVICE must select an exact Paper factory case');
const testScript='platform/tests/test_public_qemu_paper_stock_guest.mjs';
const papers3=device==='papers3';
const holdMs=Number(process.env.M5_QEMU_PAPER_STOCK_HOLD_MS||300);
assert.ok(holdMs===300||(papers3&&holdMs===500),'PaperS3 factory supports the 300 ms short and 500 ms native-parity cases');
const firmware=papers3 ? {
  release:'PaperS3 Factory V0.5',
  bytes:1439168,
  sha256:'d6733a0ca378f95335fa5fba4d4d992fb1dd97c17557b20e9aebfca08ba6d624',
  flashSha256:'ea1fdd4b3ee20db6b27fcd74f9e3a4bc538195075b3dfdd30f5e266764265788',
} : {
  release:'PaperDIY Factory V1.0 source build with second-start NVS',
  sourceCommit:'71748ca831af4c67b18d63822fda45d1a2a1a739',
  sourceSha256:'66afa47fc117ee47d4be3e9364370bac73f1ba15422acb5eda32c4f8bf04e730',
  nvsSha256:'239b35c93efb68c25310e28d8c9ddd3034693e08b678db9fa2227bb9d09c9b58',
  bytes:16777216,
  sha256:'beea3d73db277023fa4e363bbe103da6e024a9ea4b0db758f2bf7703b1c58b25',
  flashSha256:'beea3d73db277023fa4e363bbe103da6e024a9ea4b0db758f2bf7703b1c58b25',
};
const buttonCases={
  a:{roi:[9,620,110,66],before:'281674960fca31aa288ae5e253a9ff43a7dc72f41787ebf00e883192da04d34c',
    held:'5592213546177ac7b0c980641c96ff49804d8987500522fc1c4c4920a5ac0ae7'},
  b:{roi:[9,731,110,66],before:'e04a60459b17faf54ea45d91122a0a8bafc504c3f42c5536a7b880c9e0cd56c2',
    held:'633588a6efb5f6c4fec7cb96766bec27c1c223efadbb8b254e44b2c1b6d28ca6'},
};

await runPublicStockGuest({device,board:'m5'+device,firmware,testScript,exercise:async({page,canvas,origin,waitFrame,report,output,timeout})=>{
  await canvas.scrollIntoViewIfNeeded();
  await page.waitForFunction(papers3=>{
    const serial=stockGuestRuntime.serial;
    return serial.includes(papers3?'board_M5PaperS3':'board_M5PaperDIY')
      && (papers3 || serial.includes('Display ready: 540x960'));
  },papers3,{timeout});
  report.frames=[];
  if(papers3){
    const roi=[78,296,77,89];
    const baseline='5792f0aeebe868663bf681d080c61efe0bd920470f2a57e4199f21770cb18127';
    const first=await waitFrame(baseline,roi);
    // The icon can first match during the factory application's EPD startup.
    // Wait for a later complete instance while the clock task updates the
    // panel. Keep the actual pointer pulse unchanged.
    await page.waitForFunction(sequence=>stockGuestRuntime.lastFrame?.sequence>sequence+24,first.sequence,{timeout});
    const before=await waitFrame(baseline,roi);
    report.factory_readiness={first,before};
    report.touch_gesture={requested_hold_ms:holdMs,
      scope:holdMs===500?'native-factory-oracle-parity':'short-touch'};
    await page.evaluate(()=>{
      globalThis.stockPaperInputs=[];
      stockGuestShell.on('touch',({x,y,down})=>stockPaperInputs.push({x,y,down,observed_at_ms:performance.now()}));
    });
    const tap=async(x,y)=>{
      const point=await page.evaluate(async({origin,x,y})=>{
        const {Vector3}=await import(new URL('platform/web/vendor/three/three.module.js',origin));
        const {display,viewer}=stockGuestShell;
        const ndc=display.panel.localToWorld(new Vector3(((x+0.5)/display.width-0.5)*display.size[0],
          (0.5-(y+0.5)/display.height)*display.size[1],0)).project(viewer.camera);
        const rect=viewer.renderer.domElement.getBoundingClientRect();
        return [rect.left+(ndc.x+1)*rect.width/2,rect.top+(1-ndc.y)*rect.height/2];
      },{origin,x,y});
      const firstIndex=await page.evaluate(()=>stockPaperInputs.length);
      await page.mouse.move(...point);await page.mouse.down();
      try{await page.waitForTimeout(holdMs);}finally{await page.mouse.up();}
      const inputs=await page.evaluate(firstIndex=>stockPaperInputs.slice(firstIndex),firstIndex);
      assert.deepEqual(inputs.map(item=>item.down),[true,false]);
      for(const input of inputs)assert.ok(Math.abs(input.x-x)<=2&&Math.abs(input.y-y)<=2);
      return {inputs,model_hold_ms:inputs[1].observed_at_ms-inputs[0].observed_at_ms};
    };
    const neutral=await tap(270,400);
    await page.waitForFunction(sequence=>stockGuestRuntime.lastFrame?.sequence>sequence+24,before.sequence,{timeout});
    const unchanged=await waitFrame(baseline,roi);
    assert.ok(unchanged.sequence>before.sequence&&unchanged.sessionId===before.sessionId);
    report.neutral_touch={roi,...neutral,unchanged};
    const positive=await tap(113,347);
    report.positive_touch={roi,...positive};
    const after=await waitFrame('05d016cfbd40f9cf998104146948b3ea6c93016e9519304aba0185d1389376f3',roi);
    assert.ok(after.sequence>unchanged.sequence&&after.sessionId===unchanged.sessionId);
    report.frames.push({roi,before:unchanged,after,expected_changed_pixels:607,...positive});
  }else{
    for(const [key,region] of Object.entries(buttonCases)){
      const other=buttonCases[key==='a'?'b':'a'];
      const before=await waitFrame(region.before,region.roi);
      await canvas.focus();await page.keyboard.down(key);
      let held,independent;
      try{
        held=await waitFrame(region.held,region.roi);
        independent=await waitFrame(other.before,other.roi);
        assert.ok(held.sequence>before.sequence&&independent.sequence>=held.sequence);
      }finally{await page.keyboard.up(key);}
      const released=await waitFrame(region.before,region.roi);
      assert.ok(released.sequence>held.sequence);
      assert.ok([held,independent,released].every(frame=>frame.sessionId===before.sessionId));
      report.frames.push({key,roi:region.roi,before,held,released,other_roi:other.roi,independent,
        expected_changed_pixels:533});
    }
  }
  assert.ok(report.frames.every(item=>item.before.width===540&&item.before.height===960));
  await canvas.screenshot({path:resolve(output,'paper-factory-model.png')});
}});
