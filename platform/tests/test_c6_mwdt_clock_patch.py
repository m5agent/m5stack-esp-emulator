"""Replay actual C6 PCR/MWDT C paths and check source-clock deadlines."""
from pathlib import Path
import re,subprocess,os,unittest,shutil,tempfile,argparse
ROOT=Path(__file__).resolve().parents[2]
FIXTURE=Path(__file__).with_name('fixtures')/'c6_mwdt_clock'
PATCH=ROOT/'patches/qemu-esp32c6-uiflow2-adapters/0017-c6-mwdt-pcr-clock.patch'
STUB=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#define MAX(a,b) ((a)>(b)?(a):(b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define REG32(n,a) enum { A_##n=a, R_##n=(a)/4 };
#define FIELD(r,f,s,l) enum { R_##r##_##f##_SHIFT=s }; static const uint32_t R_##r##_##f##_MASK=(uint32_t)(((UINT64_C(1)<<l)-1)<<s);
#define FIELD_EX32(v,r,f) (((v)&R_##r##_##f##_MASK)>>R_##r##_##f##_SHIFT)
#define FIELD_DP32(v,r,f,d) (((v)&~R_##r##_##f##_MASK)|(((uint32_t)(d)<<R_##r##_##f##_SHIFT)&R_##r##_##f##_MASK))
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define QEMU_CLOCK_VIRTUAL 0
#define OBJECT_CHECK(t,o,n) ((t*)(o))
typedef void Object;
typedef int ResetType;
typedef uint64_t hwaddr;
typedef struct {int unused;} SysBusDevice;
typedef struct {int unused;} SysBusDeviceClass;
typedef struct {int unused;} MemoryRegion;
typedef struct {bool pending;uint64_t deadline;} QEMUTimer;
typedef unsigned *qemu_irq;
typedef struct {uint64_t hz;void *sink;} Clock;
static uint64_t now;
static uint64_t qemu_clock_get_ns(int c) {return now;}
static void timer_mod_ns(QEMUTimer *t,uint64_t n) {t->pending=true;t->deadline=n;}
static void timer_del(QEMUTimer *t) {t->pending=false;}
static void qemu_irq_raise(qemu_irq p) {if(p)(*p)++;}
'''
MAIN=r'''
static ESPTimgState a,b;
static ESP32C6PcrState pcr;
static unsigned irq_count,reset_count;
static void choose(int tg,unsigned select,bool enabled) {
 esp32c6_pcr_write(&pcr,tg?0x50:0x44,(select<<20)|(enabled?1u<<22:0),4);
}
static void init_wdt(ESPTimgState *s,bool external) {
 esp_timg_reset_hold(s,0);s->wdt.interrupt_irq=&irq_count;s->wdt.reset_irq=&reset_count;s->wdt.int_enabled=true;
#ifdef AFTER
 if(!external)s->wdt.external_clock=false;
#endif
 if(external) esp_timg_set_wdt_clock(s,40000000);
 s->wdt.prescaler_mirror=20000u<<16;
 s->wdt.stage_mirror[0]=10000;s->wdt.stage_mirror[1]=20000;
 esp_wdt_update_config(&s->wdt,(1u<<31)|(1u<<29)|(2u<<27)|(1u<<22));
}
static void deadline(ESPTimgState *s,uint64_t n) {assert(s->wdt.counter.timer.pending);if(s->wdt.counter.timer.deadline!=n)fprintf(stderr,"actual=%llu expected=%llu\n",(unsigned long long)s->wdt.counter.timer.deadline,(unsigned long long)n);assert(s->wdt.counter.timer.deadline==n);}
int main(int argc,char **argv) {
 assert(argc==2);int test=atoi(argv[1]);now=0;
#ifdef AFTER
 Clock clocks[2]={{.sink=&a},{.sink=&b}};pcr.wdt_clock[0]=&clocks[0];pcr.wdt_clock[1]=&clocks[1];
#endif
 esp32c6_pcr_reset_hold(&pcr,0);
 init_wdt(&a,test>1);init_wdt(&b,true);
 switch(test) {
 case 0:deadline(&a,2500000000ULL);break; /* legacy APB unchanged */
 case 1:esp_wdt_update_config(&a.wdt,a.wdt.config0|(1u<<22)|(1u<<21));esp_wdt_feed(&a.wdt);deadline(&a,5000000000ULL);break;
 case 2:assert(pcr.regs[0x44/4]==(1u<<22)&&pcr.regs[0x50/4]==(1u<<22));break;
 case 3:deadline(&a,5000000000ULL);break;
 case 4:choose(0,1,true);deadline(&a,2500000000ULL);break;
 case 5:choose(0,2,true);esp_wdt_update_stage(&a.wdt,0,875,true);esp_wdt_feed(&a.wdt);deadline(&a,1000000000ULL);break;
 case 6:now=1000000000ULL;choose(0,1,true);deadline(&a,3000000000ULL);assert(a.wdt.current_stage==0);break;
 case 7:now=1000000000ULL;choose(0,0,false);assert(!a.wdt.counter.timer.pending);now=11000000000ULL;choose(0,0,true);deadline(&a,15000000000ULL);break;
 case 8:esp_wdt_update_stage(&a.wdt,0,2000,true);esp_wdt_update_stage(&a.wdt,1,4000,true);now=1000000000ULL;esp_wdt_cb(&a.wdt);assert(irq_count==1&&a.wdt.current_stage==1);deadline(&a,3000000000ULL);now=1500000000ULL;choose(0,1,true);deadline(&a,2250000000ULL);assert(a.wdt.current_stage==1);break;
 case 9:now=1000000000ULL;choose(0,0,false);now=2000000000ULL;esp_wdt_feed(&a.wdt);assert(!a.wdt.counter.timer.pending);now=4000000000ULL;choose(0,0,true);deadline(&a,9000000000ULL);break;
 case 10:choose(0,2,true);esp_wdt_update_stage(&a.wdt,0,875,true);esp_wdt_feed(&a.wdt);for(int i=1;i<=100;i++){now=i*100000ULL;choose(0,2,true);}now=800000000ULL;choose(0,0,false);assert(a.wdt.counter.value==700);choose(0,2,true);deadline(&a,1000000000ULL);break;
 case 11:now=1000000000ULL;esp_wdt_update_prescaler(&a.wdt,40000u<<16);deadline(&a,9000000000ULL);assert(a.wdt.counter.value==2000);break;
 case 12:now=1000000000ULL;esp_wdt_update_stage(&a.wdt,0,6000,true);deadline(&a,3000000000ULL);now=2000000000ULL;esp_wdt_update_stage(&a.wdt,0,8000,true);deadline(&a,4000000000ULL);break;
 case 13:now=1000000000ULL;esp_wdt_update_stage(&a.wdt,0,1000,true);assert(!a.wdt.counter.timer.pending);choose(0,1,true);assert(!a.wdt.counter.timer.pending);esp_wdt_feed(&a.wdt);deadline(&a,1250000000ULL);break;
 case 14:choose(1,1,true);deadline(&a,5000000000ULL);deadline(&b,2500000000ULL);break;
 case 15:esp_wdt_update_prescaler(&a.wdt,0);esp_wdt_update_stage(&a.wdt,0,4,true);esp_wdt_feed(&a.wdt);deadline(&a,100);break;
 case 16:esp_wdt_update_prescaler(&a.wdt,65535u<<16);esp_wdt_update_stage(&a.wdt,0,UINT32_MAX,true);esp_wdt_feed(&a.wdt);deadline(&a,7036767041945625ULL);break;
 case 17:choose(0,1,true);esp_timg_reset_hold(&a,0);assert(!a.wdt.counter.timer.pending&&!a.wdt.current_stage);init_wdt(&a,true);choose(0,0,true);deadline(&a,5000000000ULL);break;
 case 18:now=250001;choose(0,0,false);now=1000250001;choose(0,0,true);deadline(&a,6000000000ULL);break;
 case 19:choose(0,3,true);assert(!a.wdt.counter.timer.pending);now=1000000000;choose(0,0,true);deadline(&a,6000000000ULL);break;
 case 20:now=1000000000;esp_wdt_update_config(&a.wdt,a.wdt.config0&~(1u<<31));choose(0,1,true);assert(!a.wdt.counter.timer.pending);esp_wdt_update_config(&a.wdt,a.wdt.config0|(1u<<31));deadline(&a,3500000000ULL);break;
 case 21:now=250001;esp_wdt_write_prescaler(&a.wdt,(20000u<<16)|1);assert(!(a.wdt.prescaler_mirror&1));deadline(&a,5000250001ULL);now=350002;esp_wdt_update_config(&a.wdt,a.wdt.config0|(1u<<22));deadline(&a,5000250001ULL);now=400003;esp_wdt_update_config(&a.wdt,a.wdt.config0|(1u<<22));deadline(&a,5000250001ULL);esp_wdt_write_prescaler(&a.wdt,(20000u<<16)|1);deadline(&a,5000400003ULL);break;
 case 22:a.wdt.wkey=0;now=250001;esp_wdt_write_prescaler(&a.wdt,(40000u<<16)|1);assert(a.wdt.prescaler_mirror==(20000u<<16));deadline(&a,5000000000ULL);break;
 case 23: /* Disabled is an action; every stage still restarts counting. */
  for(int i=0;i<4;i++)a.wdt.stage_mirror[i]=1;
  esp_wdt_update_config(&a.wdt,(1u<<31)|(1u<<22));esp_wdt_feed(&a.wdt);
  for(int i=0;i<16;i++){deadline(&a,(i+1)*500000ULL);now=(i+1)*500000ULL;esp_wdt_cb(&a.wdt);assert(!irq_count&&!reset_count);deadline(&a,now+500000ULL);assert(a.wdt.current_stage==(i+1)%4);}break;
 case 24: /* OFF -> INT has independent 2 + 3 tick holds. */
  for(int i=0;i<4;i++)a.wdt.stage_mirror[i]=i+2;
  esp_wdt_update_config(&a.wdt,(1u<<31)|(1u<<27)|(1u<<22));esp_wdt_feed(&a.wdt);
  deadline(&a,1000000);now=1000000;esp_wdt_cb(&a.wdt);assert(!irq_count);deadline(&a,2500000);now=2500000;esp_wdt_cb(&a.wdt);assert(irq_count==1);deadline(&a,4500000);break;
 case 25: /* Zero is retained in registers but cannot loop at one instant. */
  for(int i=0;i<4;i++)a.wdt.stage_mirror[i]=0;
  esp_wdt_update_config(&a.wdt,(1u<<31)|(1u<<22));esp_wdt_feed(&a.wdt);
  for(int i=0;i<16;i++){assert(a.wdt.stage[i%4]==0);deadline(&a,(i+1)*500000ULL);now=(i+1)*500000ULL;esp_wdt_cb(&a.wdt);deadline(&a,now+500000ULL);assert(!irq_count&&!reset_count);}break;
 case 26: /* Zero hold follows actual divider/source and pauses at the gate. */
  for(int i=0;i<4;i++)a.wdt.stage_mirror[i]=0;
  esp_wdt_update_config(&a.wdt,(1u<<31)|(1u<<22));choose(0,1,true);esp_wdt_update_prescaler(&a.wdt,1u<<16);esp_wdt_feed(&a.wdt);deadline(&a,13);
  choose(0,1,false);assert(!a.wdt.counter.timer.pending);now=1000000000;choose(0,1,true);deadline(&a,1000000013);break;
 default:abort();
 }
 printf("PASS actual C C6 MWDT %d\n",test);return 0;
}
'''
def fn(text,name):
 m=re.search(r'(?:static\s+)?(?:inline\s+)?[\w *]+\b'+re.escape(name)+r'\([^;]*?\)\n\{',text);assert m,name
 start=m.start();openidx=text.index('{',m.start());depth=0
 for i in range(openidx,len(text)):
  if text[i]=='{':depth+=1
  if text[i]=='}':
   depth-=1
   if depth==0:return text[start:i+1]+'\n'
 raise AssertionError(name)
def header(p):return re.sub(r'^#(?:include|pragma).*\n','',p.read_text(),flags=re.M)
def build(src,out,after):
 t=(src/'hw/timer/esp_timg.c').read_text();p=(src/'hw/misc/esp32c6_pcr.c').read_text()
 code=STUB+header(src/'include/hw/timer/esp_timg.h')+header(src/'include/hw/misc/esp32c6_pcr.h')
 code+= ''.join(fn(t,n) for n in ('esp_virtual_counter_update','esp_virtual_counter_alarm_in_ticks','esp_virtual_counter_reset'))
 code+=t[t.index('static inline uint64_t esp_wdt_ext_clk_frequency'):t.index('/**\n * Functions related to T0 timer registers')]
 code+=fn(t,'esp_timg_reset_hold')
 if after:code+='static void clock_update_hz(Clock *c,uint64_t hz) {c->hz=hz;esp_timg_set_wdt_clock(c->sink,hz);}\n'
 else:code+='static void esp_timg_set_wdt_clock(ESPTimgState *s,uint64_t hz) {}\nstatic void esp_wdt_write_prescaler(ESPWdtState *w,uint32_t v) {w->prescaler_mirror=v;}\n'
 code+=p[p.index('REG32(PCR_MSPI_CLK_CONF'):p.index('static uint64_t esp32c6_pcr_read')]
 code+=fn(p,'esp32c6_pcr_write')+fn(p,'esp32c6_pcr_reset_hold')+MAIN
 c=out.with_suffix('.c');c.write_text(code)
 args=['cc','-std=c11','-g','-O1','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-unused-const-variable','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 if after:args+=['-DAFTER']
 subprocess.run([*args,str(c),'-o',str(out)],check=True,capture_output=True,text=True)
 return out
@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'C compiler and git required')
class C6MwdtClockTests(unittest.TestCase):
 def test_actual_c_before_after(self):
  with tempfile.TemporaryDirectory(prefix='m5-c6-wdt-') as temp:
   out=Path(temp);before=out/'preimage';after=out/'source'
   shutil.copytree(FIXTURE,before);shutil.copytree(FIXTURE,after)
   includes=['--include='+name for name in ('hw/timer/esp_timg.c','include/hw/timer/esp_timg.h','hw/misc/esp32c6_pcr.c','include/hw/misc/esp32c6_pcr.h')]
   subprocess.run(['git','apply',*includes,'--check',str(PATCH)],cwd=after,check=True,capture_output=True)
   subprocess.run(['git','apply',*includes,str(PATCH)],cwd=after,check=True,capture_output=True)
   subprocess.run(['git','apply',*includes,'--reverse','--check',str(PATCH)],cwd=after,check=True,capture_output=True)
   for label,is_after in [('before',False),('after',True)]:
    try:binary=build(after if is_after else before,out/label,is_after)
    except subprocess.CalledProcessError as error:self.fail(error.stderr)
    for case in range(27):
     with self.subTest(version=label,case=case):
      result=subprocess.run([str(binary),str(case)],capture_output=True,text=True,timeout=10,
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
      if is_after or case in (0,1,4,13,20):
       self.assertEqual(result.returncode,0,result.stderr)
       self.assertIn('PASS actual C C6 MWDT',result.stdout)
      else:
       self.assertNotEqual(result.returncode,0,result.stdout)
       self.assertIn('assert',result.stderr.lower())

 def test_preceding_candidate_off_stage_negative(self):
  with tempfile.TemporaryDirectory(prefix='m5-c6-wdt-off-') as temp:
   out=Path(temp);source=out/'source';shutil.copytree(FIXTURE,source)
   includes=['--include='+name for name in ('hw/timer/esp_timg.c','include/hw/timer/esp_timg.h','hw/misc/esp32c6_pcr.c','include/hw/misc/esp32c6_pcr.h')]
   subprocess.run(['git','apply',*includes,str(PATCH)],cwd=source,check=True,capture_output=True)
   subprocess.run(['git','apply',str(FIXTURE/'unsafe-off-stage.patch')],cwd=source,check=True,capture_output=True)
   try:binary=build(source,out/'unsafe-off',True)
   except subprocess.CalledProcessError as error:self.fail(error.stderr)
   for case in (23,24,25,26):
    with self.subTest(case=case):
     result=subprocess.run([str(binary),str(case)],capture_output=True,text=True,timeout=10,
       env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
     self.assertNotEqual(result.returncode,0,result.stdout)
     self.assertIn('assert',result.stderr.lower())

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--patch',type=Path,default=PATCH)
 args,remaining=parser.parse_known_args();PATCH=args.patch.resolve()
 unittest.main(argv=[__file__,*remaining])
