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
    async waitUntilOnly({minimumObserved, allowedUrlPart, timeoutMs = 30000}) {
      const deadline = Date.now() + timeoutMs;
      let live = [];
      while (true) {
        const known = new Set(targets.keys());
        const response = await cdp.send('Target.getTargets');
        live = (response.targetInfos || []).filter(target => target.type === 'worker' && known.has(target.targetId))
          .map(target => ({target_id:target.targetId, url:target.url}));
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
    // Chrome can retain an engine Worker target for just over 30 seconds after
    // iframe removal on macOS. Keep a bounded receipt window while still
    // requiring every observed target to disappear.
    async waitUntilClosed({minimumObserved, timeoutMs = 60000}) {
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
