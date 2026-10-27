// U165, original Unit 8Servos; this is not U222/U223 8Servos2.
// +X right, +Y power-terminal end, +Z male servo-header side; millimetres.
export const spec={
 id:'8servos',name:'Unit 8Servos',sku:'U165',size:[24,55,11.5],
 nominalMm:[24,55,10.5],sourceTableMm:[55,24,10.5],
 cadEnvelopeMm:[24,55,8],visualEnvelopeMm:[24,55,11.5],
 mountY:-15.8,mountingHoles:[[-8,-15.8],[8,-15.8]],mountingBoreMm:4.92,
 grove:{position:[0,-27.15,1.4],face:'bottom',w:10,h:5.2,depth:6.5,color:0xa9363d},
 header:{pitch:2.54,firstX:3.1,firstY:12.65,pairPitch:5.55,baseZ:-.95,baseDepth:2.5,pinTopZ:7.5},
 terminal:{position:[0,27.54,2.65],width:15.8,pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['HPWR','GND','GND','5V']},
};
export const CHANNELS=Array.from({length:8},(_,i)=>({
 number:i,id:'servo-'+i,y:spec.header.firstY-Math.floor(i/2)*spec.header.pairPitch-(i%2)*spec.header.pitch,
}));
