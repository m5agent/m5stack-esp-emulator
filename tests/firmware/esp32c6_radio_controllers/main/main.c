#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* Observed C6 controller windows, not guest function or ISR substitutions. */
#define REG(a) (*(volatile uint32_t *)(a))
#define BLE_BASE 0x600a9400
static uint8_t input[16] __attribute__((aligned(4)));
static uint8_t output[16] __attribute__((aligned(4)));
static uint8_t rx_buffer[512] __attribute__((aligned(4)));
static volatile uint32_t rx_descriptor[3] __attribute__((aligned(4)));

static int encrypt(const uint8_t *key, const uint8_t *plain,
                   const uint8_t *expected)
{
    memcpy(input, plain, 16);
    memset(output, 0xa5, 16);
    for (unsigned i = 0; i < 4; i++) {
        uint32_t word;
        memcpy(&word, key + i * 4, 4);
        REG(BLE_BASE + 0x10 + i * 4) = word;
    }
    REG(BLE_BASE + 0x08) = 1;
    REG(BLE_BASE + 0x0c) = 16;
    REG(BLE_BASE + 0x20) = (uintptr_t)input;
    REG(BLE_BASE + 0x24) = (uintptr_t)output;
    REG(BLE_BASE + 0xb8) = 3;
    __sync_synchronize();
    REG(BLE_BASE + 0x04) = 1;
    for (unsigned i = 0; i < 10 && !REG(BLE_BASE + 0xc4); i++) {
        vTaskDelay(pdMS_TO_TICKS(1) + 1);
    }
    __sync_synchronize();
    if (!REG(BLE_BASE + 0xc4) || memcmp(output, expected, 16)) {
        printf("C6_RADIO_AES_FAIL done=%lu first=%02x\n",
               (unsigned long)REG(BLE_BASE + 0xc4), output[0]);
        return 1;
    }
    return 0;
}

void app_main(void)
{
    int failed = 0;
    puts("C6_RADIO_START");
    uint32_t before = REG(0x600ad000);
    vTaskDelay(pdMS_TO_TICKS(20));
    uint32_t delta = REG(0x600ad000) - before;
    if (!delta) { puts("C6_RADIO_TIMER_FAIL"); failed = 1; }
    else { printf("C6_RADIO_TIMER_PASS delta_us=%lu\n", (unsigned long)delta); }

    /* A peerless controller must not invent an access point or RX packet. */
    memset(rx_buffer, 0xa5, sizeof(rx_buffer));
    rx_descriptor[0] = (1u << 31) | sizeof(rx_buffer);
    rx_descriptor[1] = (uintptr_t)rx_buffer;
    rx_descriptor[2] = (uintptr_t)rx_descriptor;
    REG(0x600a4084) = (uintptr_t)rx_descriptor;
    vTaskDelay(pdMS_TO_TICKS(150));
    REG(0x600a4084) = 0;
    int changed = 0;
    for (unsigned i = 0; i < sizeof(rx_buffer); i++) changed |= rx_buffer[i] != 0xa5;
    if (changed || rx_descriptor[0] != ((1u << 31) | sizeof(rx_buffer))) {
        puts("C6_RADIO_PEERLESS_FAIL"); failed = 1;
    } else puts("C6_RADIO_PEERLESS_PASS");

    /* NIST SP 800-38A F.1.1 AES-128 ECB first block. */
    static const uint8_t key[16] = {0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,
                                  0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c};
    static const uint8_t plain[16] = {0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,
                                    0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a};
    static const uint8_t cipher[16] = {0x3a,0xd7,0x7b,0xb4,0x0d,0x7a,0x36,0x60,
                                     0xa8,0x9e,0xca,0xf3,0x24,0x66,0xef,0x97};
    static const uint8_t zero[16] = {0};
    static const uint8_t zero_cipher[16] = {0x66,0xe9,0x4b,0xd4,0xef,0x8a,0x2c,0x3b,
                                          0x88,0x4c,0xfa,0x59,0xca,0x34,0x2b,0x2e};
    if (encrypt(key, plain, cipher) || encrypt(zero, zero, zero_cipher)) failed = 1;
    else puts("C6_RADIO_AES_PASS vectors=2");
    memset(output, 0xa5, 16);
    REG(BLE_BASE + 0x08) = 7;
    REG(BLE_BASE + 0x04) = 1;
    if (REG(BLE_BASE + 0xc4) || output[0] != 0xa5) {
        puts("C6_RADIO_AES_UNSUPPORTED_FAIL"); failed = 1;
    } else puts("C6_RADIO_AES_UNSUPPORTED_PASS");
    uint32_t first = REG(0x600b2808), varied = 0;
    for (unsigned i = 0; i < 32; i++) varied |= first ^ REG(0x600b2808);
    if (!varied) { puts("C6_RADIO_RNG_REGISTER_FAIL"); failed = 1; }
    else puts("C6_RADIO_RNG_REGISTER_PASS");
    uint8_t random_bytes[64];
    esp_fill_random(random_bytes, sizeof(random_bytes));
    varied = 0;
    for (unsigned i = 1; i < sizeof(random_bytes); i++) {
        varied |= random_bytes[0] ^ random_bytes[i];
    }
    if (!varied) { puts("C6_RADIO_RNG_API_FAIL"); failed = 1; }
    else puts("C6_RADIO_RNG_API_PASS");
    if (!failed) puts("C6_RADIO_READY");
}
