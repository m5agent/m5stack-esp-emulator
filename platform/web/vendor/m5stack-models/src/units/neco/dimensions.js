// U163's own six-view drawing and product photographs, millimetres.
// Undimensioned outline control points, package spacing and travel are appearance estimates.
export const spec=Object.freeze({
 id:'neco',name:'Unit Neco',sku:'U163',size:[47.1,44.6,10.1],
 nominalMm:[44.6,43,10.1],geometrySource:'own-dimensioned-parametric',
 pcbThicknessMm:1,outerHoleSpacingMm:43,innerHoleSpacingMm:28,
 ports:{grove:{position:[3.5,-7.7,-8.75],face:'back',role:'input'},out:{position:[-3.5,-7.7,-8.75],face:'back',role:'output'}},
 button:{id:'button',position:[8.6,12.7,-1.42],rotationZ:-.58,travelMm:.15},
 defaults:{},configurations:[{id:'assembled',name:'完整猫耳灯板',options:{}}],configurationSchema:{},
 scope:'Visual geometry, physical input intent and independent external LED states only.'
});
export const mountingCenters=Object.freeze([[-21.5,-20.2],[21.5,-20.2],[-14,-17.6],[14,-17.6]]);
export const mountingRadiiMm=Object.freeze([1.05,1.05,.85,.85]);
// Centres read from the exact-product orthographic front view, using its 47.1/44.6 datums.
const leftDrawingPixels=[[685,137],[628,193],[574,253],[526,314],[481,377],[439,442],[400,509],[363,578],[329,647],[296,717],[267,787],[239,858],[213,930],[189,1002],[166,1075],[143,1148],[121,1221]];
const left=leftDrawingPixels.map(([x,y])=>({x:(x-768)/29.55,y:22.3-(y-39)/29.55}));
const path=[...left.toReversed(),{x:0,y:22.3-(103-39)/29.55},...left.map(p=>({x:-p.x,y:p.y}))];
export const pixels=Object.freeze(path.map((p,i)=>{
 const a=path[Math.max(0,i-1)],b=path[Math.min(path.length-1,i+1)];
 return Object.freeze({...p,number:i+1,angle:i===17?0:Math.atan2(b.y-a.y,b.x-a.x)-Math.PI/2});
}));
// Seventeen real decoupling packages, positions inferred from own front photograph.
export const capacitorPositions=Object.freeze([
 {x:0,y:17.4,angle:0},
 ...[1,3,5,7,9,11,13,15].flatMap(i=>{
  const p=left[i],length=Math.hypot(p.x,p.y+19),inward=[-p.x/length,-(p.y+19)/length];
  return[-1,1].map(side=>({x:side*(p.x+inward[0]*2.8),y:p.y+inward[1]*2.8,angle:side*(Math.atan2(left[Math.min(16,i+1)].y-left[Math.max(0,i-1)].y,left[Math.min(16,i+1)].x-left[Math.max(0,i-1)].x)-Math.PI/2)}));
 })
]);
