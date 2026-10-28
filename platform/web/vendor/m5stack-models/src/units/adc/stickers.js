import{printedArtwork}from'../../modeling/artwork.js';import{spec}from'./dimensions.js';
const back=new URL('./artwork/back.png',import.meta.url).href,polarity=new URL('./artwork/polarity.png',import.meta.url).href;
export function addBack(host,film){return printedArtwork(host,{target:film,url:back,size:spec.labels.back.size,position:spec.labels.back.position,face:'back',depth:.07,name:'ADC U013 own02 ADS1100 rear information reference redraw',artworkKind:'reference-redraw'})??[];}
export function addPolarity(host,film){return printedArtwork(host,{target:film,url:polarity,size:spec.labels.polarity.size,position:spec.labels.polarity.localPosition,depth:.07,name:'ADC U013 own05/06 positive-negative plug reference redraw',artworkKind:'reference-redraw'})??[];}
