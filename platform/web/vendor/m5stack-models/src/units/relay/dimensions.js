export const spec={
 id:'relay',name:'Relay',sku:'U023',
 // The product table and native CAD describe the 8 mm chassis. The linked
 // mechanical drawing separately dimensions the assembled package at 14.6 mm.
 size:[24,48,14.6],nominalMm:[24,48,8],cadEnvelopeMm:[24,48,8],visualEnvelopeMm:[24,48,14.6],mountY:-12,
 grove:{position:[0,-23.65,1.4],color:0x20272a},
 relay:{size:[15.5,10.5,11.8],position:[0,-.95,-1.2],pinTrimEvidence:'Assembled short tails inferred; the untrimmed 3.5 mm datasheet leads cannot extend through the selected native rear cover.'},
 terminal:{pitch:3.96,pinX:[-3.96,0,3.96],names:['COM','NO','NC'],position:[0,9.05,8.3],width:12.0,wallTop:8.3,pinTop:5.65,plugTop:8.9},
 source:{chassis:'Official U023 assembled STL and model size.png: 24×48×8 mm chassis',relay:'Official linked HK4100F p7: 15.5×10.5×11.8 mm; original shell aperture x±7.75, y[-6.2,4.3]',assembly:'Official U023 model size.png: 14.6 mm total and 12.9 mm terminal/accessory depth from chassis rear',terminal:'Official U023 schematic J2 Socket_3.96x3p: 1 COM, 2 NO, 3 NC; front photo confirms left-to-right order',estimated:'PCB outline/height, connector wall thickness, contact depths, plug cavities and shortened solder tails are photo-derived visual estimates; no production-fit claim'},
};
