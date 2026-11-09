import {mark} from '../../modeling/parts.js';

// Reference redraw from M5Stack's C139 rear product photos. Large verified
// labels and recognizable blocks are redrawn on the separate label carrier.
export function addRearArtwork(body, openings) {
  const width = 63.2;
  const height = 115.6;
  const centerY = -0.66;
  const artwork = mark(body, width, height, [0, centerY, -3.845], (ctx, w, h, scale) => {
    const black = '#292722';
    const blue = '#087eaf';
    const pink = '#bf2b59';
    const text = (label, x, y, size, color = black, weight = 700) => {
      ctx.fillStyle = color;
      ctx.font = `${weight} ${size}px Arial, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x, y);
    };
    const box = (x, y, width, height, fill, stroke) => {
      ctx.beginPath();
      ctx.roundRect(x, y, width, height, 0.75);
      ctx.fillStyle = fill;
      ctx.fill();
      if (stroke) {
        ctx.lineWidth = 0.35;
        ctx.strokeStyle = stroke;
        ctx.stroke();
      }
    };
    const trace = (color, points) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 0.26;
      ctx.moveTo(...points[0]);
      for (const point of points.slice(1)) ctx.lineTo(...point);
      ctx.stroke();
    };

    ctx.save();
    ctx.scale(w / 64, h / 116);
    ctx.beginPath();
    ctx.roundRect(0, 0, 64, 116, 3);
    ctx.clip();
    ctx.fillStyle = '#f1eee6';
    ctx.fillRect(0, 0, 64, 116);
    ctx.fillStyle = '#adca29';
    ctx.fillRect(0, 0, 64, 10);
    text('PAPER ·', 23.7, 5.45, 8.4, black, 400);
    text('S3', 51.3, 5.45, 8.4);
    text('Model Name: M5PAPERS3', 13.4, 13.1, 1.45);
    text('CE', 6.5, 19.7, 4.7, black, 500);
    text('FCC', 7.5, 25.4, 4.1, black, 500);

    box(37, 11.4, 25, 42.5, '#ddded7', black);
    text('E', 55.6, 22.4, 18.5, '#3c7b72', 800);
    text('Ink', 55.7, 31.3, 5.6);
    trace('#8d8f87', [[38.8, 13.2], [60.1, 51.6]]);
    text('4.7″', 50.2, 41.7, 8.6, '#df234d');
    text('16-Level', 45, 47.1, 2.2);
    text('960×540', 45.6, 50.4, 3.1);
    text('ET047TC1', 46.9, 52.5, 1.8);

    box(25, 22, 10.1, 28.3, '#cfe2e8');
    for (const [i, signal] of [
      'DB0:G6', 'DB1:G14', 'DB2:G7', 'DB3:G12', 'DB4:G9', 'DB5:G11',
      'DB6:G8', 'DB7:G10', 'XSTL:G13', 'XLE:G15', 'CKV:G18', 'SPV:G17', 'PWR:G45',
    ].entries()) text(signal, 30.05, 23.6 + i * 2.1, 1.35);

    ctx.save();
    ctx.translate(5.8, 62.5);
    ctx.rotate(-Math.PI / 2);
    box(-11.5, -3.75, 23, 7.5, '#f8f1e9', pink);
    text('BATTERY', 0, 0, 4);
    text('Li-Po', 20.5, -1, 4.2);
    text('1800mAh', 21, 2.35, 1.9);
    ctx.restore();

    trace(pink, [[19, 32], [19, 53], [24, 58], [24, 75], [15, 84]]);
    trace(pink, [[6, 75], [6, 82], [14, 84], [22, 81], [27, 81]]);
    trace(blue, [[35, 36], [36, 54], [44, 61], [50, 61], [58, 56]]);
    trace(blue, [[43, 68], [55, 68], [60, 65]]);
    trace(pink, [[41, 73], [49, 73], [56, 78], [56, 87]]);
    for (let i = 0; i < 5; i++) {
      const x = 35.4 + i * 1.45;
      trace(blue, [[x, 75.7], [x, 88 + i * 1.8], [x + 6, 94 + i * 1.8], [52.9, 94 + i * 1.8]]);
    }

    for (const [x, y, width, label, color] of [
      [17, 25, 7.1, 'MT3608', '#df3152'], [17, 39, 6.8, 'SW', blue],
      [27, 54.6, 8.1, 'SY8089', '#80508e'], [16, 58, 6.8, 'SW', blue],
      [18, 78.5, 8.6, 'LGS4056H', '#b74555'], [28.4, 74.2, 7.2, 'BMI270', blue],
      [52.3, 55.8, 12.8, 'CAP. TOUCH', blue], [57.2, 65.2, 7.6, 'BM8563', '#c04a75'],
      [51.1, 79, 8.5, '16M FLASH', '#373636'], [21, 97.5, 8.5, 'PMS150G', '#80912b'],
    ]) {
      box(x - width / 2, y - 1.9, width, 3.8, color);
      text(label, x, y, 1.36, '#fff9ef');
    }
    box(35.3, 64.7, 11, 7.9, '#cb3d29');
    text('ESP', 40.8, 68.7, 4.1, '#fff9ef');
    text('ESP32-S3R8', 40.8, 74.5, 2.15, '#b63b29');
    text('M5', 58, 77.6, 5.1, blue, 500);
    text('STACK', 58, 81.1, 1.65);
    text('PORT', 19.7, 87.05, 1.8, '#5b6027');
    text('BATTERY', 9.5, 93.4, 1.5, '#aa263d');

    box(52, 96.4, 10.1, 7.8, '#222423');
    text('MICRO', 57.05, 98.15, 1.35, '#fffdf5');
    text('SD', 57.05, 101.65, 4.2, '#fffdf5');
    box(1.1, 107.2, 15, 7.8, blue);
    text('ANTENNA', 8.6, 111.3, 2.5, '#fffdf5');
    box(49.5, 107.2, 8.5, 7.8, '#6cc2d8');
    text('USB-C', 53.75, 111.25, 2.15);
    text('STATUS', 60.2, 114.45, 1.26, pink);
    ctx.restore();

    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    for (const {cx, cy, w, h, r} of openings) {
      ctx.beginPath();
      const openingX = (width / 2 - cx - w / 2) * scale;
      const openingY = (height / 2 + centerY - cy - h / 2) * scale;
      ctx.roundRect(openingX, openingY, w * scale, h * scale, (r ?? w / 2) * scale);
      ctx.fill();
    }
    ctx.restore();
  }, 'back');
  artwork.name = 'PaperS3 rear artwork reference redraw';
  artwork.userData.artworkKind = 'reference-redraw';
  artwork.material.depthWrite = false;
  artwork.raycast = () => {};
}
