#include <Arduino.h>
#include "esp_mac.h"
#include "esp_efuse.h"
#include "esp_efuse_table.h"
#include "esp_ieee802154.h"
#include <cstring>
static void show(const char *name,esp_err_t rc,uint8_t *x,size_t n) {
 Serial.printf("IDENTITY name=%s rc=%d bytes=",name,rc);for(size_t i=0;i<n;i++)Serial.printf("%02x",x[i]);Serial.println();
}
void setup(){
 Serial.begin(115200);delay(100);
 uint8_t efuse[8]={},wifi[6]={},eui[8]={};
 show("factory",esp_efuse_mac_get_default(efuse),efuse,8);
 show("sta",esp_read_mac(wifi,ESP_MAC_WIFI_STA),wifi,6);
 show("ieee",esp_read_mac(eui,ESP_MAC_IEEE802154),eui,8);
 bool valid=wifi[0]==2 && memcmp(eui,wifi,3)==0 && eui[3]==255 && eui[4]==254 && memcmp(eui+5,wifi+3,3)==0;
 Serial.printf("IDENTITY_API result=%s\n",valid?"PASS":"FAIL");
 esp_err_t enabled=esp_ieee802154_enable();
 Serial.printf("IEEE_ENABLE rc=%d\n",enabled);
 esp_err_t set=esp_ieee802154_set_extended_address(eui);uint8_t read[8]={};
 esp_err_t get=esp_ieee802154_get_extended_address(read);
 Serial.printf("IEEE_ADDRESS set=%d get=%d result=%s\n",set,get,valid && memcmp(eui,read,8)==0?"PASS":"FAIL");
 Serial.println("IDENTITY_PROBE_DONE");
}
void loop(){delay(100);}
