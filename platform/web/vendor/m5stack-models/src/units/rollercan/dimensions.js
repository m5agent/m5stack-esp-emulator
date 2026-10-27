// U188 standard slip-ring version. +Y is the rotating top; the OLED is on -Y.
// The fixed Grove mouth defines +Z. The native STL fixes a neutral rotor phase,
// which need not equal the arbitrary phase in each official product photograph.
export const spec={
 id:'rollercan',name:'Unit RollerCAN',sku:'U188',variant:'standard-slip-ring',
 size:[40,40,40],nominalMm:[40,40,40],visualEnvelopeMm:[41,40,41],
 coordinateConvention:'+X right, +Y rotating top, +Z fixed Grove front; OLED faces bottom (-Y)',
 motor:{diameter:41,height:14.8,bottomY:-4.8,topY:10,shaftDiameter:16,shaftProjection:2.5,shaftBoreDiameter:12.6},
 grove:{position:[0,-15.15,19.8],face:'front',w:10.2,h:4.9,depth:6.6,color:0xb12625},
 groveTop:{id:'grove-top',position:[0,15.65,19.8],face:'front',w:10.2,h:4.9,depth:6.6,color:0xb12625},
 lcd:{position:[0,-19.2,0],resolution:[64,48],activeMm:[13.4112,10.0584],diagonalInch:.66},
 press:{center:[0,-20,-14.4],travelMm:.25},
 can:{faceX:19.8,rowsY:[-11.85,-15.95],width:16.6,height:4.05,depth:7.2},
 debug:{position:[0,-14.1,-19.85],width:8.1,height:2.8,depth:4.2,pitch:1.25},
 keymap:{Space:'press',KeyA:'press'},
};
