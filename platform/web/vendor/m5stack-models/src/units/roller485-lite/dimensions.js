// U182-Lite bare-motor version without slip ring. +Y is the rotating top; the OLED is on -Y.
// The fixed Grove mouth defines +Z. The native STL fixes the stationary shell datum,
// which need not equal the arbitrary phase in each official product photograph.
export const spec={
 id:'roller485-lite',name:'Unit Roller485-Lite',sku:'U182-Lite',variant:'lite-no-slip-ring',
 size:[40,40,40],nominalMm:[40,40,40],visualEnvelopeMm:[41,30,41],cadEnvelopeMm:[40,15.200000762939453,40.024444580078125],
 coordinateConvention:'+X right, +Y rotating top, +Z fixed Grove front; OLED faces bottom (-Y)',
 motor:{diameter:41,height:14.8,bottomY:-4.8,topY:10,shaftDiameter:16,shaftProjection:2.5,shaftBoreDiameter:12.6},
 grove:{position:[0,-15.15,19.8],face:'front',w:10.2,h:4.9,depth:6.6,color:0xb12625},
 lcd:{position:[0,-19.2,0],resolution:[64,48],activeMm:[13.4112,10.0584],diagonalInch:.66},
 press:{center:[0,-20,-14.4],travelMm:.25},
 debug:{position:[0,-14.1,-19.85],width:8.1,height:2.8,depth:4.2,pitch:1.25},
 terminal:{position:[19.8,-13.2,0],width:16,height:7.2,depth:7.4,pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['GND','PVIN','RS485_A','RS485_B']},
 keymap:{Space:'press',KeyA:'press'},
};
