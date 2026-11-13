#include <stdio.h>
#include <string.h>
#include "esp_mac.h"
#include "esp_efuse.h"
#include "esp_efuse_table.h"
#include "esp_rom_efuse.h"
static void show(const char *label,int rc,unsigned char *mac){printf("%s rc=%d mac=",label,rc);for(int i=0;i<6;++i)printf("%02x",mac[i]);puts("");}
void app_main(void) {
 unsigned char raw[6]={0},mac[6]={0},sta[6]={0},crc=0;
 int rc=esp_efuse_read_field_blob(ESP_EFUSE_MAC_FACTORY,raw,48);show("MAC_RAW",rc,raw);
 rc=esp_efuse_mac_get_default(mac);show("MAC_FACTORY",rc,mac);
 rc=esp_read_mac(sta,ESP_MAC_WIFI_STA);show("MAC_STA",rc,sta);
 esp_efuse_read_field_blob(ESP_EFUSE_MAC_FACTORY_CRC,&crc,8);
 printf("MAC_CRC stored=%02x computed=%02x\n",crc,esp_rom_efuse_mac_address_crc8(raw,6));
 puts("MAC_PROBE_READY");
}
