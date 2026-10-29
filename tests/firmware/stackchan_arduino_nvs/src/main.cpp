#include <Arduino.h>
#include <esp_system.h>
#include <esp_partition.h>
#include <nvs_flash.h>
#include <mbedtls/sha256.h>
static const char* NONCE="sc-independent-nvs-20261029-v1";
static const char* NAMESPACE="sc_nv_1029";
static const int32_t EXPECTED=0x00691029;
static void flash_digest(const char* phase) {
 const esp_partition_t* p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
 if(!p){Serial.printf("NVS_PROBE nonce=%s phase=%s partition_missing=1\n",NONCE,phase);return;}
 mbedtls_sha256_context ctx;mbedtls_sha256_init(&ctx);mbedtls_sha256_starts_ret(&ctx,0);
 uint8_t bytes[256],hash[32];esp_err_t err=ESP_OK;
 for(size_t offset=0;offset<p->size;offset+=sizeof(bytes)){
  const size_t count=min(sizeof(bytes),p->size-offset);err=esp_partition_read(p,offset,bytes,count);
  if(err!=ESP_OK)break;mbedtls_sha256_update_ret(&ctx,bytes,count);
 }
 mbedtls_sha256_finish_ret(&ctx,hash);mbedtls_sha256_free(&ctx);char hex[65];
 for(int i=0;i<32;i++)snprintf(hex+i*2,3,"%02x",hash[i]);hex[64]=0;
 Serial.printf("NVS_PROBE nonce=%s phase=%s offset=%lu bytes=%lu rc=%d sha256=%s\n",NONCE,phase,(unsigned long)p->address,(unsigned long)p->size,(int)err,hex);
}
static void mark(const char* phase,esp_err_t rc,int32_t value=-1){Serial.printf("NVS_PROBE nonce=%s phase=%s rc=%d value=%ld expected=%ld ms=%lu\n",NONCE,phase,(int)rc,(long)value,(long)EXPECTED,(unsigned long)millis());}
void setup(){
 Serial.begin(115200);delay(150);Serial.printf("NVS_PROBE nonce=%s phase=boot reset_reason=%d\n",NONCE,(int)esp_reset_reason());
 const esp_err_t init=nvs_flash_init();mark("flash_init",init);if(init!=ESP_OK){mark("done_init_failure",init);return;}
 nvs_handle_t handle=0;esp_err_t open=nvs_open(NAMESPACE,NVS_READWRITE,&handle);mark("open_before",open);if(open!=ESP_OK){mark("done_open_failure",open);return;}
 int32_t before=-1;esp_err_t read=nvs_get_i32(handle,"marker",&before);mark("read_before",read,before);nvs_close(handle);flash_digest("flash_before");
 if(read==ESP_OK&&before==EXPECTED){mark("persisted_after_reset",read,before);mark("done",read,before);return;}
 mark("ready_to_write",read,before);delay(12000);
 open=nvs_open(NAMESPACE,NVS_READWRITE,&handle);mark("open_write",open);if(open!=ESP_OK){mark("done_open_failure",open);return;}
 const esp_err_t erased=nvs_erase_key(handle,"marker");mark("erase_own_key",erased);
 const esp_err_t erased_commit=nvs_commit(handle);mark("commit_erase",erased_commit);
 const esp_err_t written=nvs_set_i32(handle,"marker",EXPECTED);mark("set_i32",written,EXPECTED);
 const esp_err_t committed=nvs_commit(handle);mark("commit_set",committed);nvs_close(handle);flash_digest("flash_after_write");
 open=nvs_open(NAMESPACE,NVS_READONLY,&handle);mark("reopen_readonly",open);int32_t after=-1;
 const esp_err_t after_read=open==ESP_OK?nvs_get_i32(handle,"marker",&after):open;mark("readback",after_read,after);if(open==ESP_OK)nvs_close(handle);
 mark("done",after_read,after);
}
void loop(){static uint32_t tick=0;if(millis()-tick>=1000){tick=millis();Serial.printf("NVS_PROBE nonce=%s phase=heartbeat ms=%lu\n",NONCE,(unsigned long)tick);}delay(10);}
