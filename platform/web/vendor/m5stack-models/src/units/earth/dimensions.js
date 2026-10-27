/** Millimetres; +X right, +Y probe tips, +Z exposed threshold-adjustment face. */
export const spec={
 id:'earth',name:'Unit Earth',sku:'U019',size:[24,64.3,8],nominalMm:[24,64.3,8],vendorDimensionOrderMm:[64.3,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,64.3,8.008],shellCenterY:-16.15,
 mountingHolesMm:[[-8,-20.15],[8,-20.15]],mountingHoleDiameterMm:5,
 grove:{position:[0,-31.8,1.4],widthMm:10,heightMm:5.2,pitchMm:2},
 trim:{axis:[0,-8.4485,3.5],visualRangeDeg:[-135,135],physicalStopAngleDeg:null},
 probe:{widthMm:12,tineWidthMm:3.95,gapMm:4.1,exposedLengthMm:32.3,thicknessMm:1,frontZ:2.2,tipY:32.15,holesPerTine:19},
 source:{dimensions:'Official U019 dimension drawing: overall 64.3 × 24 × 8 mm; shell 32 mm; exposed fork 32.3 mm; fork PCB 1 mm; tine 3.95 mm and gap 4.1 mm; two 5 mm mounting bores on 16 mm pitch, 12 mm from Grove end. Original shell CAD fixes threshold opening centre independently.',electronics:'Official U019 schematic V1.0 identifies LM393DR2G, HT7533, EARTH_PIN probe and R3 10K threshold potentiometer; no LED, MCU or ADC. Same-model photo shows blue exposed mechanical adjustment head and black open Grove socket.',inferred:'PCB internal outline/plane and concealed package placements, exact probe tip taper, hole radii/pitch, electrode material/finish, pot package/head depths and shaft/slot geometry, screw shank and Grove interior depth are visual reconstructions. No calibrated resistance/voltage/moisture mapping, mechanical end stop or manufacturing datum is asserted.'}
};
