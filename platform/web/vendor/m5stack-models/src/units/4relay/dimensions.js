export const CHANNELS=Object.freeze(Array.from({length:4},(_,i)=>Object.freeze({number:i+1,relayY:-17.7+20.2*i,terminalY:-26.45+20.2*i,ledY:-17.7+20.2*i})));
export const spec={
 id:'4relay',name:'Unit 4Relay',sku:'U097',size:[24,112,18.4],nominalMm:[24,112,18.4],cadEnvelopeMm:[24,112,8],
 mountingHolesMm:[[-8,-44],[8,-44],[-8,52],[8,52]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-55.65,1.4],face:'bottom',color:0xb62e3c},
 terminal:{positionX:2.1,matingZ:8.35,width:16.3,pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],connector:'ht3.96-4p'},
 source:{dimensions:'Official dimension drawing gives 24 x 112 mm, 8 mm shell and 18.4 mm assembled depth; native STL independently measures 24 x 112 x 8 mm.',conflict:'Same product page prose says 112 x 23 x 18 mm and 2 LEGO holes; its drawing and photographs show a 24 mm chassis with four mounting bores. Model follows drawing and unchanged native CAD.',inferred:'PCB outline/thickness, relay/connector package dimensions, terminal insertion frame and internal contacts, concealed electronics and screw angle are photo-derived appearance estimates, not manufacturing or safety dimensions.'},
};
