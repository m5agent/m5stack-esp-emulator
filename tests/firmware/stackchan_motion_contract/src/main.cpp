#include <Arduino.h>
#include <M5StackChan.h>
#include <nvs_flash.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <driver/uart.h>
#ifndef MOTION_CASE
#define MOTION_CASE 0
#endif
static constexpr const char* NONCE="stackchan-motion-deep-20261029-v2";
static bool rail=true,autoRelease=false,traceWire=false,started=false,finished=false;
static uint32_t bootCount=0,lastTelemetry=0,phaseAt=0;
static int phase=-1;
static const char* phaseName="ready";
static int targetYaw=0,targetPitch=0;
struct WireStats {uint32_t writes=0,lastUs=0,minDeltaUs=0xffffffff,maxDeltaUs=0;int goal=0,time=0,speed=0;};
static WireStats wire[3];
static portMUX_TYPE wireMux=portMUX_INITIALIZER_UNLOCKED;
extern "C" int __real_uart_write_bytes(uart_port_t,const void*,size_t);
extern "C" int __wrap_uart_write_bytes(uart_port_t port,const void* data,size_t count){
 const int result=__real_uart_write_bytes(port,data,count);
 if(port!=UART_NUM_1||result<=0)return result;
 static uint8_t buf[128];static size_t used=0;
 const auto* bytes=static_cast<const uint8_t*>(data);
 for(size_t i=0;i<(size_t)result;i++){
  const uint8_t b=bytes[i];if(used<2){if(b==0xff)buf[used++]=b;else used=0;continue;}
  if(used>=sizeof(buf)){used=0;continue;}buf[used++]=b;
  if(used<4)continue;const size_t length=buf[3]+4;
  if(length>sizeof(buf)||length<6){used=0;continue;}if(used<length)continue;
  unsigned sum=0;for(size_t n=2;n<length;n++)sum+=buf[n];
  if((sum&255)==255&&buf[2]>=1&&buf[2]<=2&&buf[4]==3&&buf[3]==9&&buf[5]==42){
   const int id=buf[2],goal=(buf[6]<<8)|buf[7],time=(buf[8]<<8)|buf[9],speed=(buf[10]<<8)|buf[11];
   const uint32_t now=(uint32_t)esp_timer_get_time();
   portENTER_CRITICAL(&wireMux);auto& s=wire[id];if(s.lastUs){const uint32_t dt=now-s.lastUs;s.minDeltaUs=min(s.minDeltaUs,dt);s.maxDeltaUs=max(s.maxDeltaUs,dt);}s.writes++;s.lastUs=now;s.goal=goal;s.time=time;s.speed=speed;const bool log=traceWire;portEXIT_CRITICAL(&wireMux);
   if(log)Serial.printf("{\"nonce\":\"%s\",\"kind\":\"wire_goal\",\"phase\":\"%s\",\"us\":%lu,\"id\":%d,\"goal_ticks\":%d,\"time_ms\":%d,\"speed_raw\":%d}\n",NONCE,phaseName,(unsigned long)now,id,goal,time,speed);
  }
  used=0;
 }
 return result;
}
static void nvsReport(const char* kind){
 nvs_handle_t h=0;const auto opened=nvs_open("servo",NVS_READONLY,&h);int32_t x=-1,y=-1;
 const auto rx=opened==ESP_OK?nvs_get_i32(h,"zero_pos_1",&x):opened,ry=opened==ESP_OK?nvs_get_i32(h,"zero_pos_2",&y):opened;if(opened==ESP_OK)nvs_close(h);
 Serial.printf("{\"nonce\":\"%s\",\"kind\":\"%s\",\"case\":%d,\"boot\":%lu,\"x\":%ld,\"y\":%ld,\"open_rc\":%d,\"x_rc\":%d,\"y_rc\":%d}\n",NONCE,kind,MOTION_CASE,(unsigned long)bootCount,(long)x,(long)y,(int)opened,(int)rx,(int)ry);
}
static bool writeZeros(int x,int y){
 nvs_handle_t h=0;auto o=nvs_open("servo",NVS_READWRITE,&h);if(o!=ESP_OK)return false;
 const auto a=nvs_set_i32(h,"zero_pos_1",x),b=nvs_set_i32(h,"zero_pos_2",y),c=nvs_commit(h);nvs_close(h);
 Serial.printf("{\"nonce\":\"%s\",\"kind\":\"calibration_write\",\"x\":%d,\"y\":%d,\"x_rc\":%d,\"y_rc\":%d,\"commit_rc\":%d}\n",NONCE,x,y,(int)a,(int)b,(int)c);return a==ESP_OK&&b==ESP_OK&&c==ESP_OK;
}
static void observe(const char* kind){
 int x=0,y=0;if(rail){const auto p=M5StackChan.Motion.getCurrentAngles();x=p.x;y=p.y;}
 WireStats sx,sy;portENTER_CRITICAL(&wireMux);sx=wire[1];sy=wire[2];portEXIT_CRITICAL(&wireMux);
 Serial.printf("{\"nonce\":\"%s\",\"kind\":\"%s\",\"case\":%d,\"boot\":%lu,\"phase\":\"%s\",\"ms\":%lu,\"target_ddeg\":[%d,%d],\"sdk_ddeg\":[%d,%d],\"sdk_feedback_expected\":%s,\"auto_release\":%s,\"wire_count\":[%lu,%lu],\"wire_last\":[[%d,%d,%d],[%d,%d,%d]],\"wire_dt_us\":[[%lu,%lu],[%lu,%lu]]}\n",NONCE,kind,MOTION_CASE,(unsigned long)bootCount,phaseName,(unsigned long)millis(),targetYaw,targetPitch,x,y,rail?"true":"false",autoRelease?"true":"false",(unsigned long)sx.writes,(unsigned long)sy.writes,sx.goal,sx.time,sx.speed,sy.goal,sy.time,sy.speed,(unsigned long)sx.minDeltaUs,(unsigned long)sx.maxDeltaUs,(unsigned long)sy.minDeltaUs,(unsigned long)sy.maxDeltaUs);
}
static void screen(){M5StackChan.Display().fillScreen(TFT_BLACK);M5StackChan.Display().setCursor(8,8);M5StackChan.Display().printf("Motion diagnostic\ncase %d boot %lu\n%s\nX:%d Y:%d",MOTION_CASE,(unsigned long)bootCount,phaseName,targetYaw,targetPitch);}
static void enter(const char* name,int x,int y,int speed){phaseName=name;targetYaw=x;targetPitch=y;screen();Serial.printf("{\"nonce\":\"%s\",\"kind\":\"target\",\"case\":%d,\"boot\":%lu,\"phase\":\"%s\",\"ms\":%lu,\"target_ddeg\":[%d,%d],\"spring_speed\":%d}\n",NONCE,MOTION_CASE,(unsigned long)bootCount,name,(unsigned long)millis(),x,y,speed);M5StackChan.Motion.move(x,y,speed);phaseAt=millis();}
struct Step{const char* name;int x,y,speed;uint32_t hold;int action;};
static const Step lifecycle[]={
 {"home",0,0,750,1600,0},{"yaw_positive",450,0,500,1800,0},{"yaw_negative",-450,0,750,1400,0},
 {"pitch_positive",0,600,500,1800,0},{"combined",600,300,750,1400,0},{"home_before_reverse",0,0,900,1600,0},
 {"reverse_forward",600,0,500,100,1},{"reverse_back",-600,0,500,1800,1},{"home_before_release",0,0,750,1700,0},
 {"auto_release_idle",0,0,750,1000,2},{"auto_release_command",450,300,750,1800,0},{"explicit_reenable",450,300,750,1600,3},
 {"torque_off_motion",-450,450,300,200,0},{"torque_off_hold",450,0,500,1500,4},{"torque_recover",450,0,500,1600,3},
 {"rail_off_motion",-450,450,500,200,0},{"rail_off_hold",600,0,900,1200,5},{"rail_on_no_torque",600,0,900,1200,6},
 {"rail_recover",0,0,750,1800,3},{"await_reset",450,450,750,2200,0}
};
static const Step calibration[]={
 {"custom_home",0,0,750,1800,0},{"custom_positive",450,450,750,1800,0},{"custom_negative",-450,0,750,1800,0},
 {"custom_pitch_limit",0,900,750,1800,0},{"custom_combined",300,300,750,1800,0},{"write_pending_zero",300,300,750,1400,7},
 {"await_reset",300,300,750,1400,0}
};
static void startStep(){
 const Step& s=MOTION_CASE==0?lifecycle[phase]:calibration[phase];
 traceWire=s.action==1;
 if(s.action==2){autoRelease=true;M5StackChan.Motion.setAutoTorqueReleaseEnabled(true);M5StackChan.Motion.setTorqueEnabled(true);}
 if(s.action==3){autoRelease=false;M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);M5StackChan.Motion.setTorqueEnabled(true);}
 if(s.action==4)M5StackChan.Motion.setTorqueEnabled(false);
 if(s.action==5){M5StackChan.setServoPowerEnabled(false);rail=false;}
 if(s.action==6){M5StackChan.setServoPowerEnabled(true);rail=true;}
 if(s.action==7){writeZeros(550,720);nvsReport("nvs_pending_reset");}
 enter(s.name,s.x,s.y,s.speed);
}
void setup(){
 Serial.begin(115200);delay(100);nvs_flash_init();nvs_handle_t h=0;if(nvs_open("sc_motion_v1",NVS_READWRITE,&h)==ESP_OK){uint32_t last=0;nvs_get_u32(h,"boot",&last);bootCount=last+1;nvs_set_u32(h,"boot",bootCount);nvs_commit(h);nvs_close(h);}
 if(MOTION_CASE==1&&bootCount==1)writeZeros(520,700);
 M5StackChan.begin();M5StackChan.Motion.setAutoAngleSyncEnabled(false);M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);autoRelease=false;
 M5StackChan.Display().setTextSize(2);M5StackChan.Display().setTextColor(TFT_WHITE,TFT_BLACK);phaseName=bootCount>1?"reset_ready":"ready";screen();nvsReport("nvs_ready");observe("ready");
 // Leave init torque=0 while awaiting the real top touch, including after reset.
}
void loop(){
 M5StackChan.update();const uint32_t now=millis();
 if(M5StackChan.TouchSensor.wasPressed()&&!started){started=true;M5StackChan.Motion.setTorqueEnabled(true);if(bootCount>1){enter("reset_home",0,0,750);phaseAt=millis();phase=-2;}else{phase=0;startStep();}}
 if(started&&!finished){
  if(phase==-2&&millis()-phaseAt>=1800){observe("reset_home_done");finished=true;}
  else if(phase>=0){const auto& s=MOTION_CASE==0?lifecycle[phase]:calibration[phase];if(millis()-phaseAt>=s.hold){observe("phase_end");phase++;const int total=MOTION_CASE==0?sizeof(lifecycle)/sizeof(Step):sizeof(calibration)/sizeof(Step);if(phase<total)startStep();else{finished=true;traceWire=false;phaseName="await_reset";observe("await_reset");}}}
 }
 if(now-lastTelemetry>=250){lastTelemetry=now;observe("sample");}
 delay(5);
}
