export const spec={
 id:'pbhub-v11',name:'Unit PbHUB v1.1',sku:'U041-B',
 size:[24,48,10.8],nominalMm:[24,48,10.8],cadEnvelopeMm:[24,48,8],mountY:-12,
 input:{id:'grove',position:[0,-23.65,1.4],face:'bottom',color:0xb62e3c},
 // Numbering follows the same-version front photograph, viewed with input down.
 // Socket turn rotates both the physical pin row and its mating frame.
 outputs:[
  {id:'grove-0',channel:0,position:[7.5,-1.8,6.5],turn:-Math.PI/2},
  {id:'grove-1',channel:1,position:[7.5,8.8,6.5],turn:-Math.PI/2},
  {id:'grove-2',channel:2,position:[5,17.2,6.5],turn:0},
  {id:'grove-3',channel:3,position:[-5,17.2,6.5],turn:0},
  {id:'grove-4',channel:4,position:[-7.5,8.8,6.5],turn:Math.PI/2},
  {id:'grove-5',channel:5,position:[-7.5,-1.8,6.5],turn:Math.PI/2},
 ],
 socket:{width:10,height:5.2,depth:6.5,uprightDepth:5.6,wall:.7,tipDepth:.65,contactLength:1.2},
 source:{
  dimensions:'Official U041-B page and linked drawing: 48 x 24 x 10.8 mm; local axes are 24 x 48 x 10.8 mm. Native assembled shell independently measures 24 x 48 x 8 mm.',
  drawing:'The U041-B product page links a drawing named U040-B_Module_Size_sch_01.png. It has the matching six-socket chassis, mounting bores and nominal dimensions; use the U041-B STL and same-version photos for version identity.',
  inferred:'PCB thickness and outline, package placement, socket interior walls, exact socket centers, latch dimensions and contact depths are reconstructed appearance estimates, not manufacturing tolerances.',
 },
};
