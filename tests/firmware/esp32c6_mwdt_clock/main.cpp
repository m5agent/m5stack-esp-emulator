#include <Arduino.h>
#include "esp_task_wdt.h"
#include "esp_intr_alloc.h"
#include "esp_timer.h"
#include "soc/interrupts.h"

static volatile uint32_t *const tg = (volatile uint32_t *)0x60008000;
static volatile uint32_t *const pcr = (volatile uint32_t *)0x60096000;
static volatile int64_t fired;
static void IRAM_ATTR alarm(void *) {
    fired = esp_timer_get_time();
    tg[0x64/4]=0x50d83aa1;
    tg[0x48/4]=0;
    tg[0x7c/4]=2;
}
static void clock_select(unsigned mux,bool enabled=true) {
    pcr[0x44/4]=(mux<<20)|(enabled?(1u<<22):0);
}
static int64_t start(unsigned mux,unsigned ticks) {
    tg[0x64/4]=0x50d83aa1;
    tg[0x48/4]=0;
    tg[0x7c/4]=2;
    clock_select(mux);
    tg[0x4c/4]=20000u<<16;
    tg[0x50/4]=ticks;
    tg[0x54/4]=10000000;
    tg[0x58/4]=10000000;
    tg[0x5c/4]=10000000;
    tg[0x70/4]|=2;
    fired=0;
    int64_t begin=esp_timer_get_time();
    tg[0x48/4]=(1u<<31)|(1u<<29)|(1u<<22);
    tg[0x60/4]=1; // Reset the stage explicitly between independent cases.
    return begin;
}
void setup() {
    Serial.begin(115200);
    delay(100);
    esp_err_t err=esp_task_wdt_deinit();
    if(err!=ESP_OK && err!=ESP_ERR_INVALID_STATE) {Serial.printf("SETUP_FAIL deinit=%x\n",err);return;}
    intr_handle_t handle=nullptr;
    err=esp_intr_alloc(ETS_TG0_WDT_LEVEL_INTR_SOURCE,ESP_INTR_FLAG_IRAM,alarm,nullptr,&handle);
    if(err!=ESP_OK) {Serial.printf("SETUP_FAIL irq=%x\n",err);return;}
    Serial.println("MWDT_PROBE_READY");
    unsigned passed=0;
    for(unsigned test=0;test<6;test++) {
        int64_t begin=start(test==1||test==5?1:test==2?2:0,test==2?875:1000);
        int64_t changed=0,resumed=0;
        if(test>=3) {
            while(esp_timer_get_time()-begin<100000 && !fired) delay(1);
            changed=esp_timer_get_time();
            if(test==3) clock_select(1);
            if(test==5) clock_select(0);
            if(test==4) {
                clock_select(0,false);
                delay(200);
                resumed=esp_timer_get_time();
                clock_select(0,true);
            }
        }
        while(!fired && esp_timer_get_time()-begin<1800000)delay(1);
        int64_t elapsed=fired?fired-begin:-1;
        int64_t expected=test==1?250000:test==2?1000000:500000;
        if(test==3)expected=250000+(changed-begin)/2;
        if(test==5)expected=500000-(changed-begin);
        if(test==4)expected=500000+(resumed-changed);
        bool pass=elapsed>=expected-20000 && elapsed<=expected+20000;
        passed+=pass;
        Serial.printf("MWDT_CASE index=%u elapsed_us=%lld expected_us=%lld changed_us=%lld result=%s pcr=%08lx\n",test,(long long)elapsed,(long long)expected,(long long)(changed?changed-begin:0),pass?"PASS":"FAIL",(unsigned long)pcr[0x44/4]);
        tg[0x48/4]=0;delay(20);
    }
    Serial.printf("MWDT_PROBE_DONE passed=%u total=6\n",passed);
}
void loop() {delay(100);}
