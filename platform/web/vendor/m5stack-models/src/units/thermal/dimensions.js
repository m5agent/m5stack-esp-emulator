export const spec={
  "id": "thermal",
  "name": "Thermal",
  "sku": "U016",
  "size": [
    24,
    32,
    8.6
  ],
  "nominalMm": [
    24,
    32,
    8.6
  ],
  "mountY": -4.0,
  "grove": {
    "position": [
      0,
      -15.65,
      1.4
    ],
    "widthMm": 10,
    "heightMm": 5.2,
    "color": 11872571
  },
  "sensorPackage": {
    "part": "MLX90640",
    "fovDeg": [110, 75],
    "centreMm": [0, 8],
    "nominalOuterDiameterMm": 9.3,
    "outerDiameterToleranceMm": 0.15,
    "renderedOuterDiameterMm": 9.2,
    "centralApertureDiameterMm": 2.6,
    "blackBodyHeightMm": 4.85,
    "packageHeightExcludingLeadsMm": 5.7,
    "topZMm": 4.6,
    "headerBottomZMm": -1.1,
    "source": "Melexis MLX90640 Rev12 p57 Fig29, 110 degree package; U016 own 8.6 mm overall / 8 mm shell drawing.",
    "appearanceInferences": "Cone recess, header small step profile, package yaw, PCB dimensions, clipped leads and solder; rendered diameter 9.2 is within the manufacturer 9.30 +/-0.15 tolerance."
  },
  "label": {
    "size": [
      18.5,
      15.2
    ],
    "position": [
      0,
      6.4,
      -4.035
    ]
  }
};
