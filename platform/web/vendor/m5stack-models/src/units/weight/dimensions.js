/** Millimetres: +X right, +Y fixed terminal end, +Z front. */
export const spec={
 id:'weight',name:'Unit Weight',sku:'U030',size:[24,32,10.2],nominalMm:[24,32,10.2],vendorDimensionOrderMm:[32,24,10.2],cadEnvelopeMm:[24,32,8],sourceTriangles:{assembly:3216,front:1532,rear:1684},
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 pcb:{thicknessMm:.8,topZ:-1.3,mountReliefRadiusMm:3.8,fixingBoreRadiusMm:3,installationInferred:true},
 grove:{position:[0,-15.9,1.4],pins:['DAT','CLK','5V','GND'],face:'bottom'},
 terminal:{widthMm:15.8,pitchMm:3.96,position:[0,16,1.3],pinX:[-5.94,-1.98,1.98,5.94],names:['A+','A-','E-','E+'],pinNumbers:[1,2,3,4],pinSizeMm:.64,roofTopZ:6.14},
 plug:{envelopeMm:[16.4,18.2,7.2],insertionDepthMm:7.4,bodyWidthMm:16.4,bodyEndY:10.8,bodyMinZ:-1.95,bodyMaxZ:5.25,pinBoreMm:[1.25,1.25],wireBoreMm:3.1,screwBoreMm:2.65,screwY:5.4,headRadiusMm:1.05,headRestRadians:[.2,-.45,.6,-.15],inferredFromOwnU030Photo:true},
 labels:{front:{size:[15.4,4.4],position:[0,11.1,6.14],filmThicknessMm:.06},back:{size:[15.8,11.8],position:[0,7.2,-3.84],filmThicknessMm:.04}},
 defaults:{terminalPlug:false},
 source:{dimensions:'Own U030 dimension drawing:24×32mm,8mm shell,10.2mm assembled depth,15.8mm fixed terminal width,Ø5mm mounts16mm apart12mm from bottom. Own CAD source0 complete3216-face assembly only; separate laid-out duplicates excluded.',hardware:'Own U030 schematic:HX711,SS8550 Y2,R1…R5,C1…C5,J1Grove DAT/CLK/VCC/GND,J2A+/A-/E-/E+. No MCU,I2C address,button,LED,display or bundled load cell/scale platform.',plug:'Exact own U030 package photograph confirms separate orange four-screw removable plug,open wire entries and screw recesses. This product-specific16.4×18.2×7.2mm appearance envelope,internal clearances and head registration are inferred from that photo and3.96mm pitch,not inherited U180 dimensions or rated fit.',inferred:'Hidden PCB outline/installed plane/thickness and component placement,connector inner walls,metal contacts/termination,plug dimensions/clamp details,adhesive film thickness,redraw font/letter registration. No manufacturing-fit,thread pitch,clamp travel/force,electrical,protocol,firmware,calibration or sensor values.'},
};
