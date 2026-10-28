/** MIT code; own authorized exact-model reference redraw rasters,not photograph pixels. */
import {printedArtwork} from '../../modeling/artwork.js';
const rear=new URL('./reference-redraw-back.png',import.meta.url).href,polarity=new URL('./reference-redraw-polarity.png',import.meta.url).href;
export function addStickers(host,film){return printedArtwork(host,{target:film,url:rear,size:[16,12],position:[0,7.8,-3.855],face:'back',depth:.08,artworkKind:'reference-redraw',name:'DAC original MCP4725 exact-model rear reference redraw'})??[];}
export function addPolarity(host,film){return printedArtwork(host,{target:film,url:polarity,size:[7.65,4.1],position:[0,2.35,2.1],depth:.05,artworkKind:'reference-redraw',name:'DAC original2P plus-left minus-right reference redraw'})??[];}
