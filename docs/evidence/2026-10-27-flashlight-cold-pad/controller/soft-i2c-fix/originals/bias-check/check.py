from pathlib import Path
import hashlib, json, shlex, subprocess

ROOT=Path.cwd(); OUT=ROOT/'.work/unit-host37-soft-i2c-bias-20261027-r1'
CANDIDATE=ROOT/'.work/unit-runtime-source-cold-pad-candidate/qemu'
OLD=ROOT/'.work/unit-runtime-source-route-history-final/qemu'
REL='hw/m5stopwatch/esp32s3_soft_i2c.c'
source=CANDIDATE/REL
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(source)
commands=[]
def run(argv,label,cwd=ROOT):
 p=subprocess.run(list(map(str,argv)),cwd=cwd,capture_output=True)
 (OUT/(label+'.stdout.txt')).write_bytes(p.stdout)
 (OUT/(label+'.stderr.txt')).write_bytes(p.stderr)
 commands.append({'label':label,'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':p.returncode})
 return p.returncode

entries=json.loads((OLD/'build/compile_commands.json').read_text())
entry=next(x for x in entries if x['file'].endswith('/'+REL))
original=entry.get('arguments') or shlex.split(entry['command'])
argv=[];i=0
while i<len(original):
 a=original[i]
 if a in ('-o','-MF','-MT','-MQ'):
  i+=2;continue
 if a in ('-c','-MMD','-MD','-MP'):
  i+=1;continue
 if REL in a:a=str(source)
 else:a=a.replace(str(OLD),str(CANDIDATE))
 argv.append(a);i+=1
argv+=['-fsyntax-only','-Werror']
syntax=run(argv,'full-tu-syntax',Path(entry['directory']))

gpio_harness=(ROOT/'.work/unit-host37-controller-c-check-20261027-r6/harness.c').read_text()
base=gpio_harness.split('int main(int argc,char**argv) {')[0]
stubs=r'''
typedef struct I2CBus { unsigned calls; } I2CBus;
static Error *error_fatal;
static int i2c_start_transfer(I2CBus *s,int addr,int read) { s->calls++;return 0; }
static void i2c_end_transfer(I2CBus *s) { s->calls++; }
static int i2c_send(I2CBus *s,int byte) { s->calls++;return 0; }
static int i2c_recv(I2CBus *s) { s->calls++;return 0xff; }
static void i2c_nack(I2CBus *s) { s->calls++; }
'''
tests=r'''
static void tested_pinmode(unsigned pin,int mode) {
 uint32_t val=g_iomux_regs[pin];val &= ~((1u<<8)|(1u<<7)|(1u<<3)|(1u<<2));
 if(mode==1)val|=(1u<<7)|(1u<<2);if(mode==2)val|=(1u<<8)|(1u<<3);
 val&=~(7u<<12);val|=(1u<<9)|(1u<<12);mux(pin,val);
 uint32_t cfg=g_regs[(0x74+pin*4)/4];mmio(0x74+pin*4,mode?cfg|(1u<<2):cfg&~(1u<<2));
 if(mode)mmio(pin<32?0x08:0x14,1u<<(pin&31));
 mmio(pin<32?0x24:0x30,1u<<(pin&31));mmio(0x554+pin*4,256);
}
static unsigned read_pin(unsigned pin) { return !!(gpio_input64()&(1ULL<<pin)); }
static void latch_low(unsigned pin) { mmio(pin<32?0x0c:0x18,1u<<(pin&31)); }
static void latch_high(unsigned pin) { mmio(pin<32?0x08:0x14,1u<<(pin&31)); }
static void dispose_for_host_test(M5StopwatchSoftI2C *s) {
 /* Only the host harness has reset the listener table. Product bridge has
  * process lifetime and no dynamic teardown API. Do not infer hot-unplug. */
 memset(g_listeners,0,sizeof(g_listeners));memset(g_listener_count,0,sizeof(g_listener_count));
#if WITH_PULLUPS
 esp32_gpio_remove_board_bias(s->sda_pullup);
 assert(snap(s->scl_pin).bias_up_count==1);
 esp32_gpio_remove_board_bias(s->scl_pullup);
#endif
 soft_i2c_instance=NULL;free(s);assert(controller.refs==1);
}
static void s3_case(unsigned sda,unsigned scl,const char *name) {
 fresh();I2CBus bus={0};m5stopwatch_soft_i2c_init_pins(&bus,sda,scl);
 M5StopwatchSoftI2C *s=soft_i2c_instance;assert(s&&s->bus==&bus&&!error_fatal);
#if WITH_PULLUPS
 assert(s->sda_pullup&&s->scl_pullup&&controller.refs==3);
 assert(snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
 assert(!snap(scl).external_seen&&!snap(scl).force_enabled);
#endif
 tested_pinmode(scl,0);tested_pinmode(sda,0);
 for(unsigned i=0;i<8;i++) {
  latch_low(scl);latch_low(sda);latch_high(scl);latch_high(sda);
 }
 unsigned reads=0;latch_low(scl);reads=(reads<<1)|read_pin(scl);
 latch_low(sda);reads=(reads<<1)|read_pin(sda);
 tested_pinmode(scl,1);Esp32GpioPadSnapshot p=snap(scl);
 reads=(reads<<1)|read_pin(scl);tested_pinmode(scl,2);
 tested_pinmode(sda,1);reads=(reads<<1)|read_pin(sda);tested_pinmode(sda,2);
 printf("case=%s sda=%u scl=%u pullups=%u probe_reads=0x%x scl_known=%u conflict=%u board_up=%u external=%u ie=%u\n",name,sda,scl,WITH_PULLUPS,reads,p.known,p.conflict,p.bias_up_count,p.external_seen,p.fun_ie);
#if WITH_PULLUPS
 assert(reads==3&&!p.known&&p.conflict&&p.bias_up_count==1&&!p.external_seen&&p.fun_ie);
 m5stopwatch_soft_i2c_set_hardware_active_on_bus(&bus);
 assert(s->hardware_active&&snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
 esp32_gpio_reset_hold(OBJECT(&controller),0);
 assert(snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
#else
 assert(reads!=3&&p.known&&!p.level&&!p.bias_up_count&&p.fun_ie);
#endif
 dispose_for_host_test(s);
}
static void esp32_case(void) {
 fresh();g_gpio_s3=false;esp32_gpio_reset_hold(OBJECT(&controller),0);
 I2CBus bus={0};m5stopwatch_soft_i2c_init_pins(&bus,21,22);
 M5StopwatchSoftI2C *s=soft_i2c_instance;
 assert(!error_fatal&&esp32_gpio_get_line(21)==1&&esp32_gpio_get_line(22)==1);
 printf("case=core2 sda=21 scl=22 pullups=%u legacy_levels=%d,%d\n",WITH_PULLUPS,esp32_gpio_get_line(21),esp32_gpio_get_line(22));
 dispose_for_host_test(s);
}
int main(void) {
 s3_case(12,11,"cores3-stackchan");s3_case(47,48,"stopwatch-atoms3r-sticks3-papermono");
 s3_case(3,2,"papercolor");s3_case(2,1,"unit-bus");esp32_case();return 0;
}
'''
results=[]
for mode,path in [('before',OUT/'esp32s3_soft_i2c.before.c'),('after',source)]:
 bridge='\n'.join(line for line in path.read_text().splitlines() if not line.startswith('#include'))
 c=OUT/(mode+'-harness.c');c.write_text(base+stubs+bridge+tests)
 exe=OUT/(mode+'-harness')
 compiled=run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-fsanitize=undefined','-O1',f'-DWITH_PULLUPS={int(mode=="after")}',c,'-o',exe],mode+'-compile')
 executed=run([exe],mode+'-run') if compiled==0 else None
 results.append({'mode':mode,'source_sha256':sha(path),'harness_sha256':sha(c),'compile_exit_code':compiled,'run_exit_code':executed})
record={'status':'PASS' if syntax==0 and all(x['compile_exit_code']==0 and x['run_exit_code']==0 for x in results) else 'FAIL',
        'scope':'Whole actual software-I2C bridge source plus actual r6 GPIO source fragments; host QOM/clock/IRQ/aux and I2C-bus method stubs. Only GPIO initialization/pad semantics under test; not real I2C endpoint, guest, stock-firmware, or hardware PASS.',
        'source_sha256':before,'source_unchanged':before==sha(source),'syntax_exit_code':syntax,
        'results':results,'commands':commands}
assert record['source_unchanged']
(OUT/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:record[k] for k in ('status','source_sha256','source_unchanged','syntax_exit_code','results')},indent=2))
