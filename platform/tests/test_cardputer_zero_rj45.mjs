// Issue #75: real generated geometry, old-source negative control and WebGL close-ups.
// Visual model only: no guest, Ethernet, physical measurements or firmware claims.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {chromium} from 'playwright';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const out=process.env.M5_RJ45_TEST_OUT || '/tmp/m5-cardputer-zero-rj45';
await mkdir(out,{recursive:true});
const prefix='/platform/web/vendor/m5stack-models/';
const target='src/devices/cardputer-zero/ports.js';
const fixed=await readFile(resolve(root,prefix.slice(1),target));
// Reverse the reviewed patch, without trusting a mutable upstream checkout.
const patch=await readFile(resolve(root,'patches/visual-models/0002-cardputer-zero-rj45-clearance.patch'));
const {mkdtemp}=await import('node:fs/promises');
const {tmpdir}=await import('node:os');
const temp=await mkdtemp(resolve(tmpdir(),'m5-rj45-preimage-'));
await mkdir(resolve(temp,dirname(target)),{recursive:true});await writeFile(resolve(temp,target),fixed);
execFileSync('git',['apply','--reverse','-'],{cwd:temp,input:patch});
const before=await readFile(resolve(temp,target));
const manifest=JSON.parse(await readFile(resolve(root,prefix.slice(1),'vendor-manifest.json'),'utf8'));
const layer=manifest.local_runtime_patches.find(row=>row.target===target);assert.ok(layer);
assert.equal(createHash('sha256').update(before).digest('hex'),layer.upstream.sha256);
assert.equal(createHash('sha256').update(fixed).digest('hex'),layer.effective.sha256);
const mime={'.js':'text/javascript','.png':'image/png','.css':'text/css','.json':'application/json'};
const server=createServer(async(req,res)=>{try{
 const name=new URL(req.url,'http://localhost').pathname;
 if(name==='/'){res.setHeader('Content-Type','text/html');res.end('<html><body style="margin:0"><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></body></html>');return;}
 if(name===prefix+target.replace('ports.js','ports-before.js')){res.setHeader('Content-Type','text/javascript');res.end(before);return;}
 const path=resolve(root,'.'+decodeURIComponent(name));if(!path.startsWith(root+'/'))throw Error('path');
 res.setHeader('Content-Type',mime[extname(path)]||'application/octet-stream');res.end(await readFile(path));
 }catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:900,height:700}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 const result=await page.evaluate(async({prefix})=>{
  const THREE=await import('three');const {CardputerZero}=await import(prefix+'src/devices/cardputer-zero/index.js');
  const {Device}=await import(prefix+'src/core/Device.js');const old=await import(prefix+'src/devices/cardputer-zero/ports-before.js');
  const current=new CardputerZero();const previous=new(class extends Device{build(){old.addPorts(this);}})();
  const points=[[-6.6,4.5],[6.6,4.5],[6.6,-1.8],[5.6,-1.8],[5.6,-3.8],[3.8,-3.8],[3.8,-5.3],[-3.8,-5.3],[-3.8,-3.8],[-5.6,-3.8],[-5.6,-1.8],[-6.6,-1.8]];
  function inspect(model){
   const shield=model.root.getObjectByName('RJ45 metal shield').clone(),liner=model.root.getObjectByName('RJ45 keyed plastic frame').clone();
   for(const mesh of[shield,liner]){mesh.material=mesh.material.clone();mesh.material.side=THREE.DoubleSide;mesh.updateMatrixWorld(true);}
   return [-1,-5,-10].flatMap(z=>points.map(([x,y],i)=>{
    const [bx,by]=points[(i+1)%points.length],normal=new THREE.Vector3(y-by,bx-x,0).normalize();
    const origin=new THREE.Vector3((x+bx)/2,(y+by)/2,z).addScaledVector(normal,-.5),ray=new THREE.Raycaster(origin,normal);
    const a=ray.intersectObject(shield)[0],b=ray.intersectObject(liner)[0];if(!a||!b)throw Error('Missing cavity wall');
    return {wall:i,z,separation:a.distance-b.distance};
   }));
  }
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setSize(900,700);document.body.append(renderer.domElement);
  const scene=new THREE.Scene();scene.background=new THREE.Color(0xe5e7eb);scene.add(new THREE.HemisphereLight(0xffffff,0x555555,3));
  const light=new THREE.DirectionalLight(0xffffff,4);light.position.set(6,12,20);scene.add(light);
  const camera=new THREE.PerspectiveCamera(38,900/700,.1,100);let active;
  window.rj45Render=(version,angle)=>{
   if(active)scene.remove(active);const model=version==='before'?previous:current;
   active=model.root.getObjectByName('RJ45 metal shield').parent.clone();active.position.set(0,0,0);active.quaternion.identity();scene.add(active);
   camera.position.set(Math.sin(angle)*18,Math.sin(angle*.7)*9,29);camera.lookAt(0,0,-4);renderer.render(scene,camera);
  };
  return {before:inspect(previous),after:inspect(current),webgl:renderer.getContext().getParameter(renderer.getContext().VERSION)};
 },{prefix});
 assert.equal(result.before.length,36);assert.ok(result.before.every(x=>Math.abs(x.separation)<1e-5),'Old source must reproduce coplanar walls');
 assert.ok(result.after.every(x=>x.separation>.199&&x.separation<.201),'Every keyed wall must have 0.2mm clearance at all sampled depths');
 for(const version of['before','after'])for(const angle of[-.45,0,.45]){await page.evaluate(({version,angle})=>window.rj45Render(version,angle),{version,angle});await page.screenshot({path:resolve(out,`${version}-${angle}.png`)});}
 assert.deepEqual(errors,[]);await writeFile(resolve(out,'report.json'),JSON.stringify({status:'PASS',category:'visual-geometry-only',...result},null,2)+'\n');
 console.log('PASS RJ45: 36 old coplanar negative controls, 36 corrected clearances, 6 WebGL views');
}finally{await browser?.close();await new Promise(r=>server.close(r));const {rm}=await import('node:fs/promises');await rm(temp,{recursive:true,force:true});}
