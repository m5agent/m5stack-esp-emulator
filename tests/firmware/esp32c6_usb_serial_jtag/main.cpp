#include <Arduino.h>
#include <HWCDC.h>
HWCDC Cdc;
static uint8_t tx[257],rx[197];
void setup(){
 Serial.begin(115200);delay(100);
 Cdc.setRxBufferSize(512);Cdc.setTxBufferSize(1024);Cdc.begin(115200);
 for(size_t i=0;i<sizeof(tx);i++)tx[i]=(i*37+19)&255;
 Serial.println("USB_PROBE_WAIT_RX");
 Cdc.print("USJ_TX_BEGIN\n");Cdc.write(tx,sizeof(tx));Cdc.print("\nUSJ_TX_END\n");
 size_t count=0;unsigned long start=millis();
 while(count<sizeof(rx)&&millis()-start<5000){if(Cdc.available())rx[count++]=Cdc.read();else delay(1);}
 bool valid=count==sizeof(rx);for(size_t i=0;i<count;i++)valid=valid&&rx[i]==((i*53+7)&255);
 Serial.printf("USJ_RX bytes=%u result=%s\n",(unsigned)count,valid?"PASS":"FAIL");
 Cdc.printf("USJ_RX_ACK bytes=%u result=%s\n",(unsigned)count,valid?"PASS":"FAIL");
 Serial.println("USB_PROBE_DONE");
}
void loop(){delay(100);}
