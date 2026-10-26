// U035-B only. Official table and mechanical drawing disagree: keep both.
export const spec={id:'cardkb',name:'CardKB v1.1',sku:'U035-B',nominalMm:[88,54,5],drawingEnvelopeMm:[84,54,6.3],pcbMm:[84,54,1],cornerRadius:5,zOrigin:3.15,
 grove:{position:[-42.05,12,.5],face:'left',w:10.8,h:5.3,depth:7.8},rgb:[-26.5,-5,-1.15],mountingHole:[-37,22,2.5],
};
const rows=[
 {y:16,x:-27,ids:['esc','1','2','3','4','5','6','7','8','9','0','backspace']},
 {y:4,x:-27,ids:['tab','q','w','e','r','t','y','u','i','o','p','fn']},
 {y:-8,x:-21,ids:['shift','a','s','d','f','g','h','j','k','l','enter']},
 {y:-20,x:-21,ids:['sym','z','x','c','v','b','n','m','comma','period','space']},
];
const labels={esc:'Esc',backspace:'Backspace',tab:'Tab',fn:'Fn',shift:'Shift',enter:'Enter',sym:'Sym',comma:',',period:'.',space:'Space',up:'↑',down:'↓',left:'←',right:'→'};
export const KEYS=rows.flatMap((r,row)=>r.ids.map((key,col)=>({id:'key-'+key,label:labels[key]??key.toUpperCase(),key,row,col,position:[r.x+col*6,r.y,-.8]})));
for(const [key,x,y]of [['up',-33,-11.5],['left',-38.3,-16.5],['right',-27,-16.5],['down',-33,-20.5]])KEYS.push({id:'key-'+key,label:labels[key],key,row:4,col:KEYS.length-46,position:[x,y,-.8]});
export const KEYMAP=Object.fromEntries(KEYS.map(k=>{
 const code=/^[a-z]$/.test(k.key)?'Key'+k.key.toUpperCase():/^\d$/.test(k.key)?'Digit'+k.key:({esc:'Escape',backspace:'Backspace',tab:'Tab',enter:'Enter',space:'Space',shift:'ShiftLeft',sym:'AltLeft',fn:'F1',comma:'Comma',period:'Period',up:'ArrowUp',down:'ArrowDown',left:'ArrowLeft',right:'ArrowRight'})[k.key];
 return [code,k.id];
}));
