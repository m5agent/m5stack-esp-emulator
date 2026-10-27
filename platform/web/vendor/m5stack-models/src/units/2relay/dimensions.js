export const spec={
 id:'2relay',name:'2Relay',sku:'U131',size:[24,56,19],nominalMm:[24,56,19],cadEnvelopeMm:[24,56,8],
 mountingHolesMm:[[-8,-16],[8,-16]],
 grove:{position:[0,-27.6,.2]},
 channels:[{number:1,relay:[.712,20.9,1.8],terminal:[1.772,11.85,10.5],led:[-8.532,12.4,2.15]},{number:2,relay:[.712,.3,1.8],terminal:[1.772,-8.75,10.5],led:[-8.532,-8.2,2.15]}],
 terminal:{pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['C','A','B','C']},
 source:{dimensions:'Official U131 drawing and product table: 56 x 24 x 19 mm. Native shell alone is 24 x 56 x 8 mm; 19 mm depth includes raised relay packages.',inferred:'PCB outline and Z, relay depth, terminal body/cavity/contact dimensions, installed plug position and screw-head shape are appearance reconstruction constrained by official shell apertures and exact-SKU photos; not production fit tolerances.',terminal:'Official U131 package photo shows two detachable orange VH3.96-4P plugs; product package list calls them HT3.96-4P. Both names refer to this visual accessory; mating/voltage ratings are not simulated.',lights:'Official specification and schematic identify two independent blue 0603 status LEDs. Models default off; only explicit external on/brightness changes appearance.'},
};
