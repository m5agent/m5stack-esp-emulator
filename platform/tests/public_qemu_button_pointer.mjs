// Browser-side geometry inspection only. Actual input is always Playwright's
// mouse, followed by original guest Button observations in the caller.
export async function findPublicButtonPointerTarget({componentId,origin,shellGlobal='buttonShell'}) {
  const {Vector3,Box3}=await import(new URL('platform/web/vendor/three/three.module.js',origin));
  const shell=globalThis[shellGlobal],viewer=shell?.viewer,component=shell?.model.find(componentId,'button');
  if(!viewer||!component||!component.interactive)throw new Error(`Interactive button unavailable: ${componentId}`);
  const canvas=viewer.renderer.domElement;
  const render=()=>new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Button pointer view did not render')),5000);
    viewer.once('render',()=>{clearTimeout(timer);resolve();});viewer.requestRender();
  });
  const preferred=component.meta.surfaceFace;
  const views=[...new Set([preferred,'front','right','left','back','top','bottom','iso','iso-back'].filter(Boolean))];
  const attempts=[];
  for(const view of views){
    viewer.setView(view,{duration:0});await render();
    viewer.fit({padding:1.15,duration:0});await render();
    shell.model.root.updateWorldMatrix(true,true);viewer.camera.updateMatrixWorld(true);
    const candidates=[],meshes=[];
    const add=(point,kind,priority=0)=>candidates.push({point,kind,priority});
    // The centre and triangle centres belong to actual mounted geometry.
    // Native flexures own weighted vertices on a shared shell instead of a cap.
    const box=new Box3().setFromObject(component.cap||component.object3d);
    if(!box.isEmpty())add(box.getCenter(new Vector3()),'cap-geometry-centre',10);
    if(component.shell?.geometry?.attributes.position&&component.weights){
      const mesh=component.shell,p=mesh.geometry.attributes.position,weights=component.weights;
      let total=0;const centre=new Vector3();
      for(let i=0;i<p.count;i++)if(weights[i]>1e-6){
        centre.addScaledVector(new Vector3().fromBufferAttribute(p,i),weights[i]);total+=weights[i];
      }
      if(total)add(centre.divideScalar(total).applyMatrix4(mesh.matrixWorld),'weighted-native-geometry-centre',20);
      meshes.push({mesh,weights});
    }else{
      const found=new Set();
      const collect=root=>root.traverse(mesh=>{
        if(mesh.isMesh&&mesh.geometry?.attributes.position&&!found.has(mesh)){
          found.add(mesh);meshes.push({mesh,weights:null});
        }
      });
      collect(component.object3d);
      // Some imported actuators register their real CAD surface outside their
      // component frame. Inspect that registration without bypassing pick().
      shell.model.root.traverse(object=>{
        if(object.userData.component===component||object.userData.componentHit?.component===component)collect(object);
      });
    }
    for(const {mesh,weights} of meshes){
      const p=mesh.geometry.attributes.position,index=mesh.geometry.index,count=index?.count||p.count;
      const triangleCount=Math.floor(count/3),step=weights?1:Math.max(1,Math.floor(triangleCount/96));
      for(let face=0;face<triangleCount;face+=step){
        const vertices=[0,1,2].map(j=>index?index.getX(face*3+j):face*3+j);
        const weight=weights?vertices.reduce((sum,i)=>sum+weights[i],0)/3:1;
        if(weight<=1e-6)continue;
        const point=vertices.reduce((sum,i)=>sum.add(new Vector3().fromBufferAttribute(p,i)),new Vector3())
          .divideScalar(3).applyMatrix4(mesh.matrixWorld);
        add(point,'actual-triangle-centre',weight);
      }
    }
    candidates.sort((a,b)=>b.priority-a.priority);
    const rect=canvas.getBoundingClientRect();
    let tested=0,occluded=0;
    for(const candidate of candidates.slice(0,512)){
      const ndc=candidate.point.clone().project(viewer.camera);
      if(ndc.z < -1||ndc.z>1||Math.abs(ndc.x)>=.99||Math.abs(ndc.y)>=.99)continue;
      const clientX=rect.left+(ndc.x+1)*rect.width/2,clientY=rect.top+(1-ndc.y)*rect.height/2;
      if(document.elementFromPoint(clientX,clientY)!==canvas){occluded++;continue;}
      tested++;
      const hit=viewer.pick({clientX,clientY});
      if(hit?.component!==component)continue;
      return {component:componentId,view,clientX,clientY,candidate_source:candidate.kind,
        projected_world_point:candidate.point.toArray(),observed_hit:{component:hit.component.path,
          mesh:hit.intersection.object.name,face_index:hit.intersection.faceIndex,
          world_point:hit.intersection.point.toArray(),distance:hit.intersection.distance},
        model_quaternion:shell.model.root.quaternion.toArray(),canvas:{left:rect.left,top:rect.top,width:rect.width,height:rect.height},
        previous_views:attempts};
    }
    attempts.push({view,candidates:candidates.length,tested,dom_occluded:occluded});
  }
  throw new Error(`No visible pointer hit for ${componentId}: ${JSON.stringify(attempts)}`);
}
