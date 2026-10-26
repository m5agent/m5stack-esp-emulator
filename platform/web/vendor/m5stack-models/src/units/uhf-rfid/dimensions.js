/** Millimetres; +X right, +Y top, +Z front RFID mark. */
export const spec={
 id:'uhf-rfid',name:'Unit UHF-RFID',sku:'U107',module:'JRD-4035',size:[48,56,11.5],nominalMm:[48,56,11.5],vendorDimensionOrderMm:[56,48,11.5],cadEnvelopeMm:[48,55.98902,11.5],visualEnvelopeMm:[48,55.98902,11.508],
 mountingHolesMm:[[-16,24],[16,24],[-16,-24],[16,-24]],mountingHoleDiameterMm:5,
 strapSlot:{position:[0,24.6],size:[24,2.4]},
 grove:{position:[0,-27.65,-.75],color:0x0091c8,widthMm:10,heightMm:6,pitchMm:2},
 source:{dimensions:'Official U107 specification 56 × 48 × 11.5 mm is length × width × depth; model axes are 48 × 56 × 11.5. Original assembly STL has a faceted 55.989 mm Y envelope.',
 assembly:'Complete official assembled shell, including seams, strap slot, four bores, rear latch windows and front snap tabs. No documented exterior buttons, LED windows, external antenna connector or USB.',
 electronics:'Product text confirms JRD-4035 with integrated ceramic antenna; official interface schematic confirms P1 Header5, J1 HY2.0 UART, R1 10K and C1/C2 100nF/22uF only.',
 inferred:'Concealed carrier/module PCB profiles, stack heights, unmarked RF shield, ceramic antenna dimensions, electrode/feedthrough geometry, passives/connector placement and Grove insertion/contact depths are visual reconstructions. No production module drawing or populated assembly datum is available.'}
};
