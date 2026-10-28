import {materials} from '../../core/index.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {roundedRect,solid,mesh} from './geometry.js';
import {spec} from './dimensions.js';
import {casing,fixing} from './shell.js';
import {electronics} from './electronics.js';
import {groves} from './connectors.js';
const rearUrl=new URL('./artwork/rear.png',import.meta.url).href,pcbUrl=new URL('./artwork/pcb.png',import.meta.url).href;
export function buildPbHub(host){const shell=casing(host),board=electronics(host),sockets=groves(host),fastener=fixing(host),cfg=spec.rearFilm,film=mesh(host.body,solid(roundedRect(...cfg.size,.15),cfg.thicknessMm),materials.plastic(0xe4e4d9,{roughness:.83}),cfg.position,'PbHub actual current manufacturer rear adhesive film');film.userData={role:'physical-label-substrate',thicknessMm:.08,registrationInferred:true};const rear=printedArtwork(host,{target:film,url:rearUrl,size:cfg.size,position:cfg.position,face:'back',depth:.14,name:'Original U041 current rear film accurate redraw',artworkKind:'reference-redraw'}),print=spec.pcbPrint,pcb=printedArtwork(host,{target:board.pcb,url:pcbUrl,size:print.size,position:print.position,depth:.14,name:'Original U041 visible PCB direct white silkscreen redraw',artworkKind:'reference-redraw'});host.pbhubAssembly={frame:shell.rear.parent,shell,board,sockets,fixing:fastener,film,ink:{rear,pcb}};host.groveSockets=sockets;host.unitStickers=[...(rear??[]),...(pcb??[])];}
