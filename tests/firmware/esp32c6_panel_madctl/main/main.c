#include <stdio.h>
#include <stdint.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static spi_device_handle_t panel;
static void transfer(int dc, const uint8_t *data, unsigned len)
{
    gpio_set_level(16, dc);
    gpio_set_level(17, 0);
    spi_transaction_t t = {.length=len*8, .tx_buffer=data};
    ESP_ERROR_CHECK(spi_device_polling_transmit(panel, &t));
    gpio_set_level(17, 1);
}
static void command(uint8_t cmd, const uint8_t *data, unsigned len)
{
    transfer(0, &cmd, 1);
    if (len) transfer(1, data, len);
}
static void window(uint8_t cmd, unsigned start, unsigned end)
{
    uint8_t data[] = {start >> 8, start, end >> 8, end};
    command(cmd, data, sizeof(data));
}
void app_main(void)
{
    for (unsigned i=0; i<3; i++) {
        const unsigned pin[]={16,17,23};
        gpio_reset_pin(pin[i]); gpio_set_direction(pin[i],GPIO_MODE_OUTPUT);
        gpio_set_level(pin[i],1);
    }
    spi_bus_config_t bus={.mosi_io_num=21,.miso_io_num=22,.sclk_io_num=20,
        .quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=64};
    spi_device_interface_config_t dev={.clock_speed_hz=1000000,.mode=0,
        .spics_io_num=-1,.queue_size=1};
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_DISABLED));
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST,&dev,&panel));
    command(0x11,NULL,0); command(0x29,NULL,0);
    uint8_t colmod=0x55;command(0x3a,&colmod,1);
    const struct { uint8_t madctl; unsigned x,y,w,h; } rotations[]={
        {0x08,52,40,135,240},{0x68,40,53,240,135},
        {0xc8,53,40,135,240},{0xa8,40,52,240,135}};
    for(unsigned r=0;r<4;r++) {
        command(0x36,&rotations[r].madctl,1);
        window(0x2a,rotations[r].x,rotations[r].x+rotations[r].w-1);
        window(0x2b,rotations[r].y,rotations[r].y+rotations[r].h-1);
        command(0x2c,NULL,0);
        uint8_t bytes[64];unsigned used=0;
        for(unsigned y=0;y<rotations[r].h;y++)for(unsigned x=0;x<rotations[r].w;x++) {
            const uint16_t colors[]={0xf800,0x07e0,0x001f,0xffff};
            unsigned corner=(y>=rotations[r].h/2)*2+(x>=rotations[r].w/2);
            uint16_t color=colors[corner];bytes[used++]=color>>8;bytes[used++]=color;
            if(used==sizeof(bytes)){transfer(1,bytes,used);used=0;}
        }
        if(used)transfer(1,bytes,used);
        printf("C6_PANEL_ROTATION_%u_READY\n",r);fflush(stdout);
        vTaskDelay(pdMS_TO_TICKS(4000));
    }
    /* Separate >128-byte DMA regression: the HP length field is 18 bits. */
    ESP_ERROR_CHECK(spi_bus_remove_device(panel));
    ESP_ERROR_CHECK(spi_bus_free(SPI2_HOST));
    bus.max_transfer_sz=512;
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO));
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST,&dev,&panel));
    unsigned r=1;
    command(0x36,&rotations[r].madctl,1);
    for(unsigned pass=0;pass<2;pass++) {
        window(0x2a,40,279);window(0x2b,53,187);command(0x2c,NULL,0);
        uint8_t bytes[352] __attribute__((aligned(4))); unsigned used=0;
        for(unsigned y=0;y<135;y++)for(unsigned x=0;x<240;x++) {
            const uint16_t colors[]={0xf800,0x07e0,0x001f,0xffff};
            uint16_t color=pass ? colors[(y>=67)*2+(x>=120)] : 0;
            bytes[used++]=color>>8;bytes[used++]=color;
            if(used==(pass ? sizeof(bytes) : 64)){transfer(1,bytes,used);used=0;}
        }
        if(used)transfer(1,bytes,used);
    }
    puts("C6_PANEL_DMA_READY");fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(4000));
    puts("C6_PANEL_READY");
}
