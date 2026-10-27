/** Millimetres; +X right, +Y speaker end, +Z front grille. */
export const spec={
 id:'asr',name:'ASR',sku:'U194',size:[24,48,16],nominalMm:[24,48,16],vendorDimensionOrderMm:[48,24,16],
 cadEnvelopeMm:[24,48,16],visualEnvelopeMm:[24,48,16.012],mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 grove:{position:[0,-23.65,-3.8],color:0x029fb8,widthMm:10,heightMm:5.2,pitchMm:2},
 speaker:{centerMm:[0,8,3.8],frameMm:[20.2,28,1],documentedImpedanceOhm:8,documentedPowerW:.8,rearLabelPrintedPowerW:1},
 microphone:{part:'GM16027P-2C320DB',type:'analog',packagePlacementInferred:true},
 source:{dimensions:'Official U194 product page: 48×24×16 mm; complete original assembled source shell matches 24×48×16 mm in model axes.',electronics:'Exact Unit ASR U194: CI-03T module, MK1 GM16027P-2C320DB analog microphone, internal SPK P1, Grove UART GND/5V/RXD/TXD. D4 RED LED is concealed; no exterior LED optical path, button or USB established.',inferred:'PCB/module/package envelopes and installed XYZ, speaker frame/cone/basket/magnet dimensions, internal P1 and fixed wire routing, microphone can/gasket/bore/mesh installation are visual reconstructions without production assembled STEP. Speaker body spec says 8Ω@0.8W; official rear sticker prints 8Ω@1W. This model does not determine electrical rating.'},
};
