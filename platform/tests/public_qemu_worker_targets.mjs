// Dedicated Worker targets are the authoritative lifetime source here.
// Playwright's Worker "close" event can lag until page teardown on macOS even
// after the Worker has already disappeared from the browser target graph.
export async function observeWorkerTargets(browser, {pollIntervalMs = 100} = {}) {
  const cdp = await browser.newBrowserCDPSession();
  const targets = new Map();
  const events = [];
  const record = targetInfo => {
    if (targetInfo.type !== 'worker') return;
    const previous = targets.get(targetInfo.targetId);
    targets.set(targetInfo.targetId, {
      targetId: targetInfo.targetId,
      type: targetInfo.type,
      url: targetInfo.url || previous?.url || '',
      createdAt: previous?.createdAt || new Date().toISOString(),
      destroyedAt: previous?.destroyedAt || null,
    });
  };
  const onCreated = ({targetInfo}) => {
    if (targetInfo.type !== 'worker') return;
    events.push({kind:'created', targetId:targetInfo.targetId, at:new Date().toISOString()});
    record(targetInfo);
  };
  const onChanged = ({targetInfo}) => record(targetInfo);
  const onDestroyed = ({targetId}) => {
    const target = targets.get(targetId);
    if (!target) return;
    target.destroyedAt ||= new Date().toISOString();
    events.push({kind:'destroyed', targetId, at:target.destroyedAt});
  };
  cdp.on('Target.targetCreated', onCreated);
  cdp.on('Target.targetInfoChanged', onChanged);
  cdp.on('Target.targetDestroyed', onDestroyed);
  await cdp.send('Target.setDiscoverTargets', {discover:true});
  return {
    async snapshotQemuTopology() {
      const {targetInfos}=await cdp.send('Target.getTargets');
      const all=targetInfos.filter(target=>target.type==='worker');
      const engines=all.filter(target=>target.url.includes('/public-qemu-engine.js'));
      const engine=engines[0];
      const pthreads=all.filter(target=>target!==engine);
      const pageParent=targetInfos.some(target=>target.type==='page'&&target.targetId===engine?.parentId);
      const ok=engines.length===1&&pthreads.length>0&&pageParent
        &&new Set(all.map(target=>target.targetId)).size===all.length
        &&pthreads.every(target=>target.url.startsWith('blob:')
          &&target.parentId===engine.parentId&&target.parentFrameId===engine.parentFrameId
          &&target.parentId!==engine.targetId);
      return {ok,engine_count:engines.length,pthread_count:pthreads.length,targets:all,
        source:'Chrome DevTools Target.getTargets'};
    },
    async waitUntilOnly({minimumObserved, allowedUrlPart, timeoutMs = 30000}) {
      const deadline = Date.now() + timeoutMs;
      let live = [];
      while (true) {
        const response = await cdp.send('Target.getTargets');
        const workers = (response.targetInfos || []).filter(target => target.type === 'worker');
        for(const target of workers)record(target);
        live = workers.map(target => ({target_id:target.targetId, url:target.url, attached:target.attached===true}));
        if (targets.size >= minimumObserved
            && (allowedUrlPart ? live.every(target => target.url.includes(allowedUrlPart)) : live.length === 0)) {
          return {ok:true, minimum_observed:minimumObserved, observed:[...targets.values()], live, events,
            allowed_url_part:allowedUrlPart, source:'Chrome DevTools Target.getTargets'};
        }
        if (Date.now() >= deadline) {
          return {ok:false, minimum_observed:minimumObserved, observed:[...targets.values()], live, events,
            allowed_url_part:allowedUrlPart, source:'Chrome DevTools Target.getTargets'};
        }
        await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
      }
    },
    // Chrome can retain an engine Worker target for more than a minute after
    // iframe removal on macOS. Keep a bounded receipt window while still
    // requiring every observed target to disappear.
    async waitUntilClosed({minimumObserved, timeoutMs = 120000}) {
      return this.waitUntilOnly({minimumObserved, allowedUrlPart:'', timeoutMs});
    },
    async detach() {
      cdp.off('Target.targetCreated', onCreated);
      cdp.off('Target.targetInfoChanged', onChanged);
      cdp.off('Target.targetDestroyed', onDestroyed);
      await cdp.detach().catch(() => {});
    },
  };
}

// Logical exit counts and the broker's actual normal termination calls must agree.
export function closedQemuPthreadBroker(cleanup) {
  const broker=cleanup?.engineOwnership?.pthreadBroker;
  return Number.isInteger(cleanup?.workersCreated)&&cleanup.workersCreated>0
    &&cleanup.disposal?.workerCountScope==='engine-pthreads'
    &&broker?.created===cleanup.workersCreated&&broker.live===0
    &&broker.terminations===broker.created&&broker.fallbackTerminations===0;
}
