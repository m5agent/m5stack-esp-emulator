/** Millimetres:+X right,+Y exposed prototype field top,+Z front. */
export const spec={
 id:'mini-proto',name:'Unit Mini Proto',sku:'U064',size:[24,32,8],nominalMm:[24,32,8],vendorDimensionOrderMm:[32,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,8],
 sourceTriangles:{assembly:3222,front:1526,rear:1696},mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 window:{size:[20,14],center:[0,7]},
 prototypeField:{columns:8,rows:6,count:48,pitchMm:2.54,freeHoleDiameterMm:1,substrateBoreDiameterMm:1.06,platingThicknessMm:.03,padDiameterMm:1.6,padThicknessMm:.025,center:[0,7],pcbTopZ:-.45,pcbThicknessMm:1,gridCountSource:'Own official straight front and oblique photos;8×6 field counted visually',inferredBoreAndInstallation:true},
 grove:{position:[0,-15.9,1.4],face:'bottom',socketMm:[10,5.2],pins:['I / MISO','O / IO','VCC','GND']},
 labels:{back:{size:[15.8,11.8],position:[0,7,-3.84]}},defaults:{rearCover:true},
 source:{
  dimensions:'Exact own U064 full source0=3222 triangles,24×32×8mm,scale1.One common translation[-397.2688293457031,-313.2234802246094,+4].Only group original faces front1526/rear1696 by directed cyclic correspondence to laid-out duplicates2/1;no face moved,removed or patched.',
  prototype:'Own official photo has8columns×6rows,48real plated bores with2.54mm pitch shown in own promo image.1mm free bore,1mm substrate thickness,barrel/ring dimensions and hidden board installation are inferred.Outer-row annuli partly under native rim in own photos;native lip retained.',
  hardware:'Own schematic is only passive P1 Header4 toJ1GROVE_IO breakout.No factory user-added circuits,raisedP1header,IC,sensor,LED,button,display oractuated joint fabricated.',
  inferred:'Hidden PCB extent/seating,1mm bore andFR4thickness,0.03mmplating,0.025mmannuli,connector terminal/fixing fit,adhesive thickness andphoto-redraw font/registration.No current,power rating,signal direction orprotocol/firmware behavior.'
 }
};
