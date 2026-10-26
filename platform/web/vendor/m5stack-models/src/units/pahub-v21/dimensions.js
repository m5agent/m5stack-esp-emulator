// U040-B-V21: millimetres, +X right, +Y top, +Z exposed PCB/socket face.
export const spec={
 id:'pahub-v21',name:'PaHUB v2.1',sku:'U040-B-V21',
 size:[24,48,10.8],nominalMm:[24,48,10.8],cadEnvelopeMm:[24,48,8],visualEnvelopeMm:[24,48,10.8],
 mountY:-12,mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 input:{id:'grove',position:[0,-23.65,1.4],face:'bottom',rotation:0},
 // Front view: upper row CH3, CH2; left side CH4, CH5; right side CH1, CH0.
 // rotation is around the front-face normal, shared by the socket and Port.
 outputs:[
  {id:'grove-0',channel:0,position:[7.3,-1.6,6.5],rotation:Math.PI/2},
  {id:'grove-1',channel:1,position:[7.3,8.3,6.5],rotation:Math.PI/2},
  {id:'grove-2',channel:2,position:[5.2,17,6.5],rotation:Math.PI},
  {id:'grove-3',channel:3,position:[-5.2,17,6.5],rotation:Math.PI},
  {id:'grove-4',channel:4,position:[-7.3,8.3,6.5],rotation:-Math.PI/2},
  {id:'grove-5',channel:5,position:[-7.3,-1.6,6.5],rotation:-Math.PI/2},
 ],
 connector:{widthMm:10,heightMm:5.2,outputDepthMm:5.8,pitchMm:2},
 dip:{ids:['dip-1','dip-2','dip-3'],rowsY:[-3.7,-4.97,-6.24],travelMm:.9},
 source:{
  dimensions:'Official U040-B-V21 table and mechanical drawing: 48 x 24 x 10.8 mm; normalized to X x Y x Z.',
  mounting:'Official drawing: two diameter 5 mm holes, 16 mm pitch, axes 12 mm from the input end.',
  channels:'Exact-version annotated photograph 4.webp; six upward-facing sockets, CH0-CH5.',
  inferred:'PCB/package thicknesses, connector wall/contact details, socket centres and DIP travel are appearance estimates from the exact-version photos and drawing, not manufacturing tolerances.',
 },
};
