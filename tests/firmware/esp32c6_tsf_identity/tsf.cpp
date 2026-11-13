#include <Arduino.h>
#include "esp_timer.h"
extern "C" uint64_t hal_get_tsf_time(int);
static volatile uint32_t *const tsf=(volatile uint32_t *)0x600ad000;
static void gate(unsigned i,bool on){tsf[(0x50+8*i)/4]=on?0x80000000u:0;}
static void load(unsigned i,uint64_t x){tsf[0x18/4]=x;tsf[0x1c/4]=x>>32;tsf[0x14/4]|=1u<<(4+i);}
static uint64_t read(unsigned i){tsf[0x14/4]|=1u<<i;uint64_t x=((uint64_t)tsf[0x24/4]<<32)|tsf[0x20/4];tsf[0x14/4]&=~(1u<<i);return x;}
void setup(){
 Serial.begin(115200);delay(100);unsigned passes=0;bool ok;
 for(unsigned i=0;i<4;i++){gate(i,false);load(i,0);}
 gate(0,true);int64_t start=esp_timer_get_time();uint64_t first=hal_get_tsf_time(0);delay(20);uint64_t delta=hal_get_tsf_time(0)-first;int64_t elapsed=esp_timer_get_time()-start;
 ok=delta>=15000 && delta<=(uint64_t)elapsed+5000;passes+=ok;Serial.printf("TSF_CASE index=0 delta_us=%llu wall_us=%lld result=%s\n",delta,elapsed,ok?"PASS":"FAIL");
 gate(0,false);load(0,4242);delay(20);ok=read(0)==4242;passes+=ok;Serial.printf("TSF_CASE index=1 result=%s\n",ok?"PASS":"FAIL");
 load(0,0xffff0000ULL);gate(0,true);tsf[0x14/4]|=1;uint32_t low=tsf[0x20/4];delay(100);uint32_t high=tsf[0x24/4];tsf[0x14/4]&=~1u;uint64_t later=read(0);ok=low>=0xffff0000u && high==0 && (later>>32)==1;passes+=ok;Serial.printf("TSF_CASE index=2 result=%s\n",ok?"PASS":"FAIL");
 gate(1,false);load(1,0x123456789abcdef0ULL);ok=read(1)==0x123456789abcdef0ULL;passes+=ok;Serial.printf("TSF_CASE index=3 result=%s\n",ok?"PASS":"FAIL");
 load(1,0);ok=read(1)==0 && !(tsf[0x14/4]&0xf0);passes+=ok;Serial.printf("TSF_CASE index=4 result=%s\n",ok?"PASS":"FAIL");
 gate(0,false);load(0,10);load(1,20);gate(1,true);delay(20);ok=read(0)==10 && read(1)>=15020;passes+=ok;Serial.printf("TSF_CASE index=5 result=%s\n",ok?"PASS":"FAIL");
 Serial.printf("TSF_PROBE_DONE passed=%u total=6\n",passes);
}
void loop(){delay(100);}
