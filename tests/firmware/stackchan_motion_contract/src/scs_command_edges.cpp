#include <Arduino.h>
#include <M5Unified.h>
#include <drivers/PY32IOExpander/PY32IOExpander.hpp>
#include <drivers/FTServo_Arduino/src/SCSCL.h>
// This fixture deliberately does not call M5StackChan.begin(): one caller owns UART1.
// The original unmodified official low-level SCSCL and PY32IOExpander drivers are used.
static constexpr const char* NONCE="stackchan-scs-edges-20261029-v2";
static SCSCL bus;
static m5::PY32IOExpander_Class power;
static int phase=0,repeat=0;static uint32_t phaseAt=0,lastSample=0;
static const char* phaseName="ready";
static bool finished=false;
static void command(const char* name,int rc){Serial.printf("{\"nonce\":\"%s\",\"kind\":\"command\",\"phase\":\"%s\",\"ms\":%lu,\"name\":\"%s\",\"rc\":%d,\"ack_state\":%u,\"io_error\":%u}\n",NONCE,phaseName,(unsigned long)millis(),name,rc,bus.getState(),bus.getLastError());}
static void sample(const char* kind){
 const int pos=bus.ReadPos(1),moving=bus.ReadMove(1),torque=bus.readByte(1,SCSCL_TORQUE_ENABLE);
 const int goal=bus.readWord(1,SCSCL_GOAL_POSITION_L),time=bus.readWord(1,SCSCL_GOAL_TIME_L),speed=bus.readWord(1,SCSCL_GOAL_SPEED_L);
 const int lo=bus.readWord(1,SCSCL_MIN_ANGLE_LIMIT_L),hi=bus.readWord(1,SCSCL_MAX_ANGLE_LIMIT_L);
 Serial.printf("{\"nonce\":\"%s\",\"kind\":\"%s\",\"phase\":\"%s\",\"ms\":%lu,\"present\":%d,\"moving\":%d,\"torque\":%d,\"goal\":%d,\"time_ms\":%d,\"speed_raw\":%d,\"min\":%d,\"max\":%d,\"mode_from_limits\":\"%s\",\"io_error\":%u}\n",NONCE,kind,phaseName,(unsigned long)millis(),pos,moving,torque,goal,time,speed,lo,hi,lo==0&&hi==0?"pwm":"position",bus.getLastError());
}
static void label(const char* name){phaseName=name;phaseAt=millis();repeat=0;M5.Display.fillScreen(TFT_BLACK);M5.Display.setCursor(8,8);M5.Display.printf("SCS official driver\n%s\nUART1 only caller",name);Serial.printf("{\"nonce\":\"%s\",\"kind\":\"phase\",\"phase\":\"%s\",\"ms\":%lu}\n",NONCE,name,(unsigned long)millis());}
static const char* phases[]={"write_home","write_move_repeat","reg_home","reg_move_repeat","sync_home","sync_move_repeat","custom_limits","pwm_mode","position_restored","restored_move","done"};
static void enter(){
 label(phases[phase]);
 if(phase==0||phase==2||phase==4){command("EnableTorque1",bus.EnableTorque(1,1));command("WritePos460Time800",bus.WritePos(1,460,800,0));}
 if(phase==1||phase==3||phase==5)command("WritePos800Time4000",bus.WritePos(1,800,4000,0));
 if(phase==6){command("Unlock",bus.unLockEprom(1));command("Min100",bus.writeWord(1,SCSCL_MIN_ANGLE_LIMIT_L,100));command("Max900",bus.writeWord(1,SCSCL_MAX_ANGLE_LIMIT_L,900));sample("limits_written");}
 if(phase==7){command("SwitchMode1",bus.SwitchMode(1,1));sample("pwm_readback");}
 if(phase==8){command("SwitchMode0",bus.SwitchMode(1,0));sample("restored_readback");}
 if(phase==9)command("RestoredWritePos650Time1000",bus.WritePos(1,650,1000,0));
 if(phase==10){sample("done");finished=true;}
 phaseAt=millis(); // Measure holds from the completed real command/diagnostic setup.
}
void setup(){
 Serial.begin(115200);M5.begin();M5.Display.setTextSize(2);M5.Display.setTextColor(TFT_WHITE,TFT_BLACK);
 const bool ready=power.begin();power.setDirection(0,true);power.setPullMode(0,m5::PY32IOExpander_Class::pull_up);power.digitalWrite(0,true);delay(250);
 const bool uart=bus.begin(UART_NUM_1,1000000,6,7);command("EnableTorque2Off",bus.EnableTorque(2,0));
 Serial.printf("{\"nonce\":\"%s\",\"kind\":\"ready\",\"power_driver\":%s,\"uart_driver\":%s,\"no_bsp_motion_thread\":true}\n",NONCE,ready?"true":"false",uart?"true":"false");
 enter();
}
void loop(){
 M5.update();
 if(!finished){
  const uint32_t elapsed=millis()-phaseAt;
  if((phase==1||phase==3||phase==5)&&repeat<7&&elapsed>=400u+repeat*200u){
   if(phase==1)command("RepeatTorque_WRITE",bus.EnableTorque(1,1));
   else if(phase==3){uint8_t one=1;command("RepeatTorque_REG_WRITE",bus.regWrite(1,SCSCL_TORQUE_ENABLE,&one,1));command("RepeatTorque_ACTION",bus.RegWriteAction(1));}
   else {uint8_t ids[]={1},one=1;bus.syncWrite(ids,1,SCSCL_TORQUE_ENABLE,&one,1);command("RepeatTorque_SYNC_WRITE_NO_ACK",0);}
   repeat++;sample("after_repeat");
  }
  const uint32_t hold=(phase==1||phase==3||phase==5)?5000:(phase==9?1400:(phase==6||phase==7||phase==8?500:1100));
  if(millis()-phaseAt>=hold){sample("phase_end");phase++;enter();}
 }
 const uint32_t now=millis();if(now-lastSample>=150){lastSample=now;sample("sample");}delay(5);
}
