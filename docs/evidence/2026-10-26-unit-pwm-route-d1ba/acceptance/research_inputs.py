"""Read existing local inputs, retain exact proof bytes; no downloads/compiler/API."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
inputs={
 'original-observation-receipt.json':ROOT/'docs/evidence/2026-10-26-unit-ledc-audio-29d8/audio/harness/initial-qom-observation-review/receipt.json',
 'original-mmio-program.py.txt':ROOT/'.work/unit-ledc-mmio-diagnostic-20261026-r1/guest_audio/mmio_program.py',
 'explicit-zero-program.py.txt':ROOT/'.work/unit-ledc-mmio-diagnostic-20261026-r1/guest_audio_explicit_zero/mmio_program.py',
 'route-diagnostic-receipt.json':ROOT/'.work/unit-pwm-route-diagnostic-20261026/receipt.json',
 'route-diagnostic.c.txt':ROOT/'.work/unit-pwm-route-diagnostic-20261026/diagnostic.c',
 'machine_pwm.c.txt':ROOT/'.work/buzzer-ledc-readback-review-20261026/machine_pwm-78ff170.c',
 'idf-ledc.c.txt':ROOT/'.work/buzzer-ledc-readback-review-20261026/idf-ledc.c',
 'idf-ledc_hal.h.txt':ROOT/'.work/buzzer-ledc-readback-review-20261026/idf-ledc_hal.h',
 'official-pin-doc.md.txt':Path('/Users/yunyu/.codex/skills/uiflow2-coder/docs/hardware/pin.md'),
 'official-buzzer-doc.md.txt':Path('/Users/yunyu/.codex/skills/uiflow2-coder/docs/unit/buzzer.md'),
 'official-button-doc.md.txt':Path('/Users/yunyu/.codex/skills/uiflow2-coder/docs/unit/button.md'),
}
(HERE/'research').mkdir(exist_ok=True);rows={}
for name,p in inputs.items():
 raw=p.read_bytes();dest=HERE/'research'/name
 if dest.exists():assert dest.read_bytes()==raw
 else:dest.write_bytes(raw)
 rows[name]={'sha256':sha(raw),'size':len(raw),'origin':'existing local exact source or bundled official UIFlow2 documentation','source':p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'uiflow2-coder bundled docs/'+p.name}
r=json.loads(inputs['original-observation-receipt.json'].read_bytes());directory=ROOT/'.work/unit-ledc-mmio-diagnostic-20261026-r1/audio-prepared-r1'
verified=[]
for row in r['zero_frequency_observations']:
 p=directory/row['body'];raw=p.read_bytes();assert sha(raw)==row['body_sha256'];state=json.loads(raw);u=state['units'][0];assert u['source']=='guest-qom' and u['available'] and u['properties']['frequency-hz']==u['properties']['duty-pct']==0
 verified.append({'name':p.name,'sha256':sha(raw),'frequency-hz':0,'duty-pct':0})
assert len(verified)==39
first=r['first_2000hz_zero_observation'];raw=(directory/first['body']).read_bytes();assert sha(raw)==first['body_sha256'];u=json.loads(raw)['units'][0];assert u['properties']['frequency-hz']==2000 and u['properties']['duty-pct']==0
# Preserve original 39 + the first later-setter observation, without rewriting JSON.
for row in r['zero_frequency_observations']+[first]:(HERE/'research'/row['body']).write_bytes((directory/row['body']).read_bytes())
# Balanced extraction is for short, existing functions only; not a C transformer.
def function(text,name):
 match=re.search(r'(?m)^[^\n]*\b'+re.escape(name)+r'\([^\n]*\)\s*\{',text);assert match,name;start=match.start();brace=text.index('{',match.start());depth=1;end=brace+1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
mp=inputs['machine_pwm.c.txt'].read_text();idf=inputs['idf-ledc.c.txt'].read_text();functions={name:function(mp,name) for name in ['mp_machine_pwm_freq_get','mp_machine_pwm_duty_get_u16','get_duty_u16']};functions.update({name:function(idf,name) for name in ['ledc_get_freq','ledc_get_duty']})
assert 'ledc_get_freq' in functions['mp_machine_pwm_freq_get'] and 'get_duty_u16' in functions['mp_machine_pwm_duty_get_u16']
for name,text in functions.items():assert not re.search(r'\b(?:ledc_set\w*|ledc_update\w*|apply_duty|reconfigure_pin|esp_rom_gpio_connect_out_signal)\s*\(',text),name
(HERE/'research/getter-functions.json').write_text(json.dumps(functions,indent=2)+'\n')
proof={'status':'LOCAL_RESEARCH_VERIFIED','original_zero_qom_observations':verified,'original_zero_count':39,'later_first_2000hz_observation':{'name':first['body'],'sha256':sha(raw),'after_explicit_zero_setter':True},'source_inputs':rows,'getter_path':'machine freq/get_u16 -> IDF ledc_get_freq/get_duty -> HAL get register functions; no LEDC set/update or GPIO-route call in extracted functions','native_getter_functions_sha256':{k:sha(v.encode()) for k,v in functions.items()},'original_timer_bug_isolation':'New caller imports neither BuzzerUnit nor Haptic/SoftTimer; proves raw PWM initialization only. No custom callback patch included.','scope':'Existing local source and evidence only; no API/network/compiler/guest. Static source-path evidence is not a dynamic native MMIO trace or proof for all firmware builds.'}
(HERE/'research-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':proof['status'],'old_zero_observations':39,'getter_functions':len(functions),'api_network_compiler_guest_calls':0}))
