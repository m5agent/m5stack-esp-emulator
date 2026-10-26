// U153 Unit 8Encoder. Official mechanical drawing; no product revision inferred
// from the V1.01 schematic filename. Coordinates: +X right, +Y switch end, +Z front.
export const spec={
 id:'8encoder',name:'Unit 8Encoder',sku:'U153',size:[24,128,25],nominalMm:[24,128,25],
 sourceTableMm:[128,24,25],cadEnvelopeMm:[24,128,10],visualEnvelopeMm:[24,128,25],
 baseShellThicknessMm:8,raisedPlatformThicknessMm:10,mountY:-52,
 mountingHoles:[[-8,-52],[8,-52]],grove:{position:[0,-63.65,.65],face:'bottom',w:10,h:5.2,depth:6.6},
 knob:{diameter:10,pitch:13,firstY:-40.6,baseZ:5.4,height:14.6,pressTravel:.35,shaftRadius:1.5,shaftTopZ:9.8,boreRadius:1.7,boreDepth:6},
 led:{x:-8.65,z:2.8,w:2.8,h:.65,depth:.55},
 slide:{center:[0,59,5],travel:2.2},
};
export const CHANNELS=Array.from({length:8},(_,i)=>({number:i+1,y:spec.knob.firstY+i*spec.knob.pitch,press:'press-'+(i+1),rotation:'rotation-'+(i+1),rgb:'rgb-'+(i+1)}));
