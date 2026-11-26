// Opt-in cross-site documentation embed for real browser guest tests.
// The parent page is served from a different origin (localhost vs 127.0.0.1)
// without COOP/COEP, matching the published docs pages. The workbench must
// isolate itself inside the iframe through its own Service Worker.
export const DOCS_EMBED_PATH = '/docs-embed/';

export function docsEmbedEnabled(env = process.env) {
  return env.M5_PUBLIC_DOCS_EMBED === '1';
}

const escapeAttribute = value => value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');

// Returns true when the request was the parent docs document. An optional
// ?src= selects a link inside the same workbench, like a docs page that
// embeds a shared example URL; any other target is rejected.
export function serveDocsEmbed(requestUrl, response, workbenchUrl) {
  const url = new URL(requestUrl, 'http://localhost');
  if (url.pathname !== DOCS_EMBED_PATH) return false;
  const base = new URL(workbenchUrl), src = new URL(url.searchParams.get('src') || base.href);
  if (src.origin !== base.origin || !src.pathname.startsWith(base.pathname)) {
    response.writeHead(400).end();
    return true;
  }
  response.writeHead(200, {'content-type':'text/html', 'cache-control':'no-store'});
  response.end('<!doctype html><meta charset="utf-8"><title>Docs embed</title>'
    + '<style>body{margin:0}iframe{border:0;width:100vw;height:100vh;display:block}</style>'
    + `<iframe allow="cross-origin-isolated" src="${escapeAttribute(src.href)}"></iframe>`);
  return true;
}

export function docsParentUrl(port, src) {
  return `http://localhost:${port}${DOCS_EMBED_PATH}` + (src ? `?src=${encodeURIComponent(src)}` : '');
}

// Navigate the top page to the docs parent and return the workbench frame.
export async function openDocsEmbed(page, {port, workbenchUrl, src, timeoutMs = 45000}) {
  const parentUrl = docsParentUrl(port, src);
  await page.goto(parentUrl, {waitUntil:'domcontentloaded'});
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const frame = page.frames().find(item => item.parentFrame() === page.mainFrame() && item.url().startsWith(workbenchUrl));
    if (frame) return {frame, parentUrl};
    if (Date.now() >= deadline) throw new Error('Docs embed iframe did not load the workbench');
    await page.waitForTimeout(100);
  }
}

export async function docsEmbedIdentity(page, frame) {
  const parent = await page.evaluate(() => ({isolated:crossOriginIsolated, shared:typeof SharedArrayBuffer, origin:location.origin}));
  const child = await frame.evaluate(() => ({isolated:crossOriginIsolated, shared:typeof SharedArrayBuffer, origin:location.origin}));
  return {parent, frame:child, iframe_allow:'cross-origin-isolated',
    ok:parent.isolated === false && parent.shared === 'undefined' && child.isolated === true
      && child.shared === 'function' && parent.origin !== child.origin};
}
