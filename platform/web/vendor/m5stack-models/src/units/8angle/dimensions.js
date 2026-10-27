// U154 Unit 8Angle, millimetres: +X right, +Y switch end, +Z knob face.
export const spec={
 id:'8angle',name:'Unit 8Angle',sku:'U154',size:[24,128,23],nominalMm:[24,128,23],
 sourceTableMm:[128,24,23],cadEnvelopeMm:[24,128,10],visualEnvelopeMm:[24,128,23],
 mountY:-52,mountingHoles:[[-8,-52],[8,-52]],
 grove:{position:[0,-63.65,.65],face:'bottom',w:10,h:5.2,depth:6.6},
 knob:{diameter:10,pitch:13,firstY:-40.6,baseZ:5.4,height:12.6,limitsDeg:[-140,140]},
 led:{x:-8.65,z:2.8,w:2.8,h:.65,depth:.55},
 slide:{center:[0,59,4.45],travel:2.2},
 source:{
  dimensions:'Official U154 table and drawing: 128 x 24 x 23 mm assembled, 8 mm perimeter shell, 10 mm knob diameter and 13 mm pitch.',
  rotation:'Official U154 annotated product photograph explicitly marks 280 degrees. Runtime uses [-140,140] degrees about a photo-derived middle position; the absolute shaft/ADC zero is not calibrated.',
  inferred:'PCB, hidden potentiometer packages, shaft/bore internals, connector walls and switch detent spacing are appearance estimates. They are not manufacturing tolerances.',
 },
};
export const CHANNELS=Array.from({length:8},(_,i)=>({number:i+1,y:spec.knob.firstY+i*spec.knob.pitch,rotation:'rotation-'+(i+1),rgb:'rgb-'+(i+1)}));
