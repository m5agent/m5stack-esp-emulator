/** Millimetres:+X right,+Y top transmit can,+Z acoustic faces. */
export const spec={
 id:'ultrasonic-io',name:'Unit Ultrasonic-IO',sku:'U098-B2',size:[24,56,15.2],nominalMm:[24,56,15.2],vendorDimensionOrderMm:[56,24,15.2],
 cadEnvelopeMm:[24.027936935424805,56.02793884277344,9],visualEnvelopeMm:[24.027936935424805,56.02793884277344,15.2],sourceTriangles:{assembly:5510,front:2466,rear:3044},
 mountingHolesMm:[[-8,-16],[8,-16]],mountingHoleDiameterMm:4.85,mountingHoleEvidence:'Own native mid-depth inner wall radius2.425mm;layered chamfer/mouth preserved,not a uniform5mm manufacturing bore claim',
 transducers:[{id:'transmit',center:[0,18.15],role:'passive-acoustic-carrier'},{id:'receive',center:[0,-3.85],role:'passive-acoustic-carrier'}],
 acoustic:{outerRadiusMm:8,innerRadiusMm:7.35,baseZ:-.35,topZ:10.7,guardZ:10.05,guardPitchMm:.55,guardWidthMm:.08,guardDepthMm:.08,guardAnchorRadiusMm:7.45,diaphragmZ:2.7,diaphragmRadiusMm:5.1,inferredDepthAndGuard:true},
 pcb:{topZ:-.45,thicknessMm:.8,componentInstallationInferred:true},
 grove:{position:[0,-27.9,1.4],face:'bottom',pins:['GND','5V','TRIG','ECHO'],color:0x171b17},
 labels:{back:{size:[16,36],position:[0,7,-4.34]}},defaults:{rearCover:true},
 source:{cad:'Exact own U098-B2 rear1(3044)+front2(2466),all5510originalfaces retained under common translation[0,-16,-1.7],scale1.Native mould tolerance24.02794×56.02794×9mm retained;displacedcopies0/3 excluded.No B1assembly/print reuse.',board:'Own GPIO RCWL-9620 carrier andown bare-boardphoto,not I2C firmware/variant inference.SOP16package andvisible passives reconstructed;hidden placement/stack dimensions inferred.No active physical controls orlights established.',acoustic:'Two16mmblack grid-covered transducers confirmed byown currentproduct/gallery.Native circularaperture centers± aroundY18.15/−3.85 retained.Case9mm andnominaltotal15.2mm separated;can top10.7mm set from nominaldepth.Guardpitch/wiredepth andinternaldiaphragm/support installation inferred fromown photo;never animated.',pinmap:'Own exact hero/rear printing statesPORT.B.I/O:GND5VTRIGECHO.The currentdoc table incorrectly saysPORT.A SDA/SCL;officialfeedback588c2040ad754aab8e946edc4cbd033d already received.No electrical/pulse/distance behavior inferred.'}
};
