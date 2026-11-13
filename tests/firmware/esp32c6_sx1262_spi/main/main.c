#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_rom_sys.h"

#define CS 23
#define SCK 20
#define MOSI 21
#define MISO 22

static spi_device_handle_t radio;
static int transfer(const unsigned char *tx, unsigned char *rx, unsigned size)
{
    spi_transaction_t t = {.length = size * 8, .tx_buffer = tx, .rx_buffer = rx};
    gpio_set_level(CS, 0);
    esp_err_t err = spi_device_polling_transmit(radio, &t);
    gpio_set_level(CS, 1);
    if (err != ESP_OK) { printf("C6_SX1262_FAIL transfer err=%d\n", err); return 1; }
    return 0;
}

static unsigned char soft_byte(unsigned char tx)
{
    unsigned char rx = 0;
    for (int i = 7; i >= 0; i--) {
        gpio_set_level(MOSI, (tx >> i) & 1);
        esp_rom_delay_us(2);
        gpio_set_level(SCK, 1);
        rx = (rx << 1) | gpio_get_level(MISO);
        esp_rom_delay_us(2);
        gpio_set_level(SCK, 0);
    }
    return rx;
}

void app_main(void)
{
    puts("C6_SX1262_START");
    gpio_reset_pin(CS);
    gpio_set_direction(CS, GPIO_MODE_OUTPUT);
    gpio_set_level(CS, 1);
    spi_bus_config_t bus = {.mosi_io_num=MOSI, .miso_io_num=MISO, .sclk_io_num=SCK,
                           .quadwp_io_num=-1, .quadhd_io_num=-1, .max_transfer_sz=64};
    spi_device_interface_config_t dev = {.clock_speed_hz=1000000, .mode=0,
                                        .spics_io_num=-1, .queue_size=1};
    if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED) != ESP_OK ||
        spi_bus_add_device(SPI2_HOST, &dev, &radio) != ESP_OK) {
        puts("C6_SX1262_FAIL bus"); return;
    }
    unsigned char tx[20]={0x1d,0x03,0x20,0}, rx[20]={0};
    if (transfer(tx, rx, sizeof(tx))) return;
    /* RadioLib 7.6.0 documents that SX1262 silicon identifies as SX1261. */
    if (memcmp(rx+4, "SX1261", 6)) {
        printf("C6_SX1262_FAIL identity first=%02x,%02x,%02x,%02x\n",rx[4],rx[5],rx[6],rx[7]); return;
    }
    puts("C6_SX1262_ID_PASS");
    /* RadioLib keeps CS low while issuing one-byte controller transactions. */
    gpio_set_level(CS,0);
    for (unsigned i=0;i<sizeof(tx);i++) {
        spi_transaction_t t={.length=8,.tx_buffer=&tx[i],.rx_buffer=&rx[i]};
        if (spi_device_polling_transmit(radio,&t)!=ESP_OK) {
            gpio_set_level(CS,1); puts("C6_SX1262_FAIL split transfer"); return;
        }
    }
    gpio_set_level(CS,1);
    if (memcmp(rx+4,"SX1261",6)) {
        puts("C6_SX1262_FAIL split identity"); return;
    }
    puts("C6_SX1262_SPLIT_PASS");
    for (unsigned char type=0;type<=1;type++) {
        unsigned char set_type[]={0x8a,type},get_type[]={0x11,0,0},reply[3];
        if (transfer(set_type,reply,sizeof(set_type)) ||
            transfer(get_type,reply,sizeof(get_type))) return;
        if (reply[2]!=type) {puts("C6_SX1262_FAIL packet type"); return;}
    }
    puts("C6_SX1262_PACKET_TYPE_PASS");
    const unsigned char wr[]={0x0d,0x07,0x40,0x37,0x49};
    unsigned char scratch[8];
    if (transfer(wr,scratch,sizeof(wr))) return;
    const unsigned char rd[]={0x1d,0x07,0x40,0,0,0};
    if (transfer(rd,scratch,sizeof(rd))) return;
    if (scratch[4]!=0x37 || scratch[5]!=0x49) {
        printf("C6_SX1262_FAIL burst read=%02x,%02x\n",scratch[4],scratch[5]); return;
    }
    puts("C6_SX1262_HW_BURST_PASS");
    spi_bus_remove_device(radio);
    spi_bus_free(SPI2_HOST);
    gpio_reset_pin(SCK); gpio_reset_pin(MOSI); gpio_reset_pin(MISO);
    gpio_set_direction(SCK,GPIO_MODE_OUTPUT);
    gpio_set_direction(MOSI,GPIO_MODE_OUTPUT);
    gpio_set_direction(MISO,GPIO_MODE_INPUT);
    gpio_set_level(SCK,0);
    gpio_set_level(CS,0);
    soft_byte(0x1d); soft_byte(0x07); soft_byte(0x40); soft_byte(0);
    unsigned char a=soft_byte(0),b=soft_byte(0);
    gpio_set_level(CS,1);
    if (a!=0x37 || b!=0x49) {
        printf("C6_SX1262_FAIL shared-state read=%02x,%02x\n",a,b); return;
    }
    puts("C6_SX1262_SHARED_STATE_PASS");
    puts("C6_SX1262_READY");
}
