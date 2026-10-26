import {printedArtwork,printedFilm} from '../../modeling/artwork.js';

// Flat official raster artwork. All coordinates are in the assembled product
// frame; the four keyboard strips are on the fixed plate between the keys.
export function addStickers(host){
 const {parts}=host;
 const add=(file,options)=>printedArtwork(host,{url:new URL(`./artwork/${file}.png`,import.meta.url).href,...options});
 for(let i=0;i<4;i++)add(`keyboard-${i+1}`,{target:parts['upper-housing'],size:[81.6,3.7856],position:[0,3.65-i*7.5,6],depth:.64,name:`Official keyboard plate legends row ${i+1}`});
 add('front-name',{target:parts['upper-housing'],size:[17.6,15.2533],position:[-31.5,18.3,9.8],depth:.45,name:'Official Cardputer-ADV front name'});
 // The factory foil is the actual continuous printed cover above the Stamp
 // assembly. Its screw and RGB apertures remain independent of the artwork.
 printedFilm(host,{url:new URL('./artwork/stamp.png',import.meta.url).href,size:[23.6,17.213],position:[27.8,16.47,9.91],parent:parts['stamp-frame'],holes:[{w:3.15,h:3.15,r:1.575,cx:3.5,cy:4.5},{w:1.9,h:1.9,r:.28,cx:7.45,cy:-6.02}],name:'Official StampS3A adhesive circuit cover'});
 add('back',{target:parts['battery-base'],size:[80.8,48.4163],position:[0,0,-9.8],face:'back',depth:.4,name:'Official Cardputer-ADV rear circuit label'});
 add('top-edge',{target:parts['upper-housing'],size:[80,9.7981],position:[0,26.8,3.7],face:'top',rotation:Math.PI,depth:.5,name:'Official Cardputer-ADV top-edge legends'});
 add('grove-side',{target:parts['upper-housing'],size:[22,9.0918],position:[-41.8,13.7,3.4],face:'left',depth:.6,name:'Official Cardputer-ADV Grove and power direction legends'});
}
