#include <Arduino.h>
#include <M5Cardputer.h>
static const char* nonce="cardputer-input-orientation-20261030-v1";
static unsigned rotation=0,stage=0,sequence=0;
static bool previous_enter=false;
static uint64_t previous_keys=~uint64_t(0);
static void state(const char* kind) {
  const auto& k=M5Cardputer.Keyboard.keysState();
  Serial.printf("{\"nonce\":\"%s\",\"kind\":\"%s\",\"seq\":%u,\"guest_ms\":%lu,\"rotation\":%u,\"width\":%u,\"height\":%u,\"color_depth\":%u,\"irq_level\":%d,\"positions\":[",nonce,kind,++sequence,millis(),rotation,M5Cardputer.Display.width(),M5Cardputer.Display.height(),unsigned(M5Cardputer.Display.getColorDepth()),digitalRead(11));
  bool first=true;for(const auto& p:M5Cardputer.Keyboard.keyList()){if(!first)Serial.print(',');first=false;Serial.printf("[%u,%u]",p.y,p.x);}
  Serial.printf("],\"fn\":%u,\"shift\":%u,\"ctrl\":%u,\"opt\":%u,\"alt\":%u,\"enter\":%u,\"backspace\":%u,\"up\":%u,\"down\":%u,\"left\":%u,\"right\":%u,\"word\":[",k.fn,k.shift,k.ctrl,k.opt,k.alt,k.enter,k.backspace,k.up,k.down,k.left,k.right);
  first=true;for(const auto c:k.word){if(!first)Serial.print(',');first=false;Serial.printf("%u",(uint8_t)c);}Serial.println("]}");
}
static void draw_rotation() {
  auto& d=M5Cardputer.Display;d.setRotation(rotation);d.setBrightness(255);d.fillScreen(0x102030u);
  auto w=d.width(),h=d.height();
  d.fillRect(0,0,12,12,0xff0000u);d.fillRect(w-12,0,12,12,0x00ff00u);
  d.fillRect(0,h-12,12,12,0x0000ffu);d.fillRect(w-12,h-12,12,12,0xffff00u);
  d.setTextColor(0xffffffu);d.setTextSize(1);d.setCursor(20,20);d.printf("ROTATION %u",rotation);
  state("rotation-full");
}
void setup(){Serial.begin(115200);delay(100);auto cfg=M5.config();cfg.clear_display=true;M5Cardputer.begin(cfg,true);Serial.printf("{\"nonce\":\"%s\",\"kind\":\"board\",\"board\":%u,\"keyboard_path\":\"official-M5Cardputer-IRQ-update\"}\n",nonce,(unsigned)M5.getBoard());draw_rotation();}
void loop(){
  M5Cardputer.update();
  uint64_t keys=0;for(const auto& p:M5Cardputer.Keyboard.keyList())keys|=uint64_t(1)<<(p.y*14+p.x);
  if(keys!=previous_keys){previous_keys=keys;state("keys");}
  const bool enter=M5Cardputer.Keyboard.keysState().enter;
  if(stage<8 && enter && !previous_enter){
    if(stage%2==0){M5Cardputer.Display.fillRect(40,50,8,8,0xff00ffu);stage++;state("rotation-partial");}
    else{stage++;if(stage<8){rotation++;draw_rotation();}else{rotation=1;draw_rotation();state("ready");}}
  }
  previous_enter=enter;
  delay(5);
}
