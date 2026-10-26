/**
 * QEMU WLAN access point emulation
 *
 * Copyright (c) 2008 Clemens Kolbitsch
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 * Modifications:
 *  2008-February-24  Clemens Kolbitsch :
 *                                  New implementation based on ne2000.c
 *  18/1/22 Martin Johnson : Modified for esp32 wifi emulation
 */

#include "qemu/osdep.h"
#include "qemu/cutils.h"
#include "qemu/error-report.h"
#include "qemu/guest-random.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "crypto/cipher.h"
#include "crypto/hmac.h"
#include "crypto/pbkdf.h"
#include "net/net.h"
#include "qemu/timer.h"

#include "hw/misc/esp32_wifi.h"
#include "esp32_wlan.h"
#include "esp32_wlan_packet.h"

// 50ms between beacons
#define BEACON_TIME 50000000
#define INTER_FRAME_TIME 5000000
#define DEBUG 0
#define DEBUG_DUMPFRAMES 0

#define WPA_KEY_INFO_KEY_TYPE BIT(3)
#define WPA_KEY_INFO_INSTALL BIT(6)
#define WPA_KEY_INFO_ACK BIT(7)
#define WPA_KEY_INFO_MIC BIT(8)
#define WPA_KEY_INFO_SECURE BIT(9)
#define WPA_KEY_INFO_ENCR_KEY_DATA BIT(12)
#define WPA_KEY_INFO_HMAC_SHA1_AES BIT(1)

#define EAPOL_VERSION 1
#define EAPOL_TYPE_KEY 3

typedef struct QEMU_PACKED eapol_header {
    uint8_t version;
    uint8_t type;
    uint16_t length;
} eapol_header;

typedef struct QEMU_PACKED eapol_key {
    uint8_t descriptor_type;
    uint8_t key_info[2];
    uint8_t key_length[2];
    uint8_t replay_counter[8];
    uint8_t nonce[32];
    uint8_t iv[16];
    uint8_t rsc[8];
    uint8_t key_id[8];
    uint8_t mic[16];
    uint8_t key_data_length[2];
} eapol_key;

static const uint8_t wpa_rsn_ie[] = {
    0x30, 0x14,
    0x01, 0x00,
    0x00, 0x0f, 0xac, 0x04,
    0x01, 0x00,
    0x00, 0x0f, 0xac, 0x04,
    0x01, 0x00,
    0x00, 0x0f, 0xac, 0x02,
    0x00, 0x00,
};

static void wpa_add_ccmp_envelope(Esp32WifiState *s,
                                  struct mac80211_frame *frame,
                                  bool group);

static uint16_t get_be16(const uint8_t *value)
{
    return ((uint16_t)value[0] << 8) | value[1];
}

static uint64_t get_be64(const uint8_t *value)
{
    uint64_t result = 0;
    int i;

    for (i = 0; i < 8; i++) {
        result = (result << 8) | value[i];
    }
    return result;
}

static void put_be16(uint8_t *output, uint16_t value)
{
    output[0] = value >> 8;
    output[1] = value;
}

static void put_be64(uint8_t *output, uint64_t value)
{
    int i;

    for (i = 7; i >= 0; i--) {
        output[i] = value;
        value >>= 8;
    }
}

static void wpa_trace(const char *format, ...)
{
    va_list arguments;

    if (!getenv("M5SW_S3_WIFI_TRACE")) {
        return;
    }
    fprintf(stderr, "[esp32s3-wifi] WPA: ");
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
}

static bool wpa_hmac_sha1(const uint8_t *key, size_t key_len,
                          const struct iovec *input, size_t input_count,
                          uint8_t output[20])
{
    g_autoptr(QCryptoHmac) hmac = NULL;
    g_autofree uint8_t *digest = NULL;
    size_t digest_len = 0;
    Error *error = NULL;

    hmac = qcrypto_hmac_new(QCRYPTO_HASH_ALGO_SHA1, key, key_len, &error);
    if (!hmac) {
        error_report_err(error);
        return false;
    }
    if (qcrypto_hmac_bytesv(
            hmac, input, input_count, &digest, &digest_len, &error) < 0) {
        error_report_err(error);
        return false;
    }
    if (digest_len != 20) {
        g_free(digest);
        return false;
    }
    memcpy(output, digest, digest_len);
    return true;
}

static bool wpa_derive_pmk(Esp32WifiState *s)
{
    Error *error = NULL;
    size_t password_len = strlen(s->wifi_password);

    if (qcrypto_pbkdf2(
            QCRYPTO_HASH_ALGO_SHA1,
            (const uint8_t *)s->wifi_password,
            password_len,
            (const uint8_t *)s->wifi_ssid,
            strlen(s->wifi_ssid),
            4096,
            s->pmk,
            sizeof(s->pmk),
            &error) < 0) {
        error_report_err(error);
        return false;
    }
    return true;
}

static bool wpa_derive_ptk(Esp32WifiState *s)
{
    static const char label[] = "Pairwise key expansion";
    uint8_t data[76];
    uint8_t counter = 0;
    uint8_t *cursor = data;
    const uint8_t *first_addr;
    const uint8_t *second_addr;
    const uint8_t *first_nonce;
    const uint8_t *second_nonce;
    size_t position;

    if (memcmp(s->ap_macaddr, s->wpa_station_addr, 6) < 0) {
        first_addr = s->ap_macaddr;
        second_addr = s->wpa_station_addr;
    } else {
        first_addr = s->wpa_station_addr;
        second_addr = s->ap_macaddr;
    }
    memcpy(cursor, first_addr, 6);
    cursor += 6;
    memcpy(cursor, second_addr, 6);
    cursor += 6;

    if (memcmp(s->anonce, s->snonce, 32) < 0) {
        first_nonce = s->anonce;
        second_nonce = s->snonce;
    } else {
        first_nonce = s->snonce;
        second_nonce = s->anonce;
    }
    memcpy(cursor, first_nonce, 32);
    cursor += 32;
    memcpy(cursor, second_nonce, 32);

    for (position = 0; position < sizeof(s->ptk); position += 20) {
        struct iovec input[] = {
            { .iov_base = (void *)label, .iov_len = sizeof(label) },
            { .iov_base = data, .iov_len = sizeof(data) },
            { .iov_base = &counter, .iov_len = 1 },
        };
        uint8_t digest[20];
        size_t copy_len = MIN(sizeof(digest), sizeof(s->ptk) - position);

        if (!wpa_hmac_sha1(s->pmk, sizeof(s->pmk),
                           input, ARRAY_SIZE(input), digest)) {
            return false;
        }
        memcpy(s->ptk + position, digest, copy_len);
        counter++;
    }
    return true;
}

static bool wpa_eapol_mic(const uint8_t *kck, eapol_key *key,
                          uint8_t *eapol, size_t length, uint8_t mic[16])
{
    struct iovec input = {
        .iov_base = eapol,
        .iov_len = length,
    };
    uint8_t digest[20];

    memset(key->mic, 0, sizeof(key->mic));
    if (!wpa_hmac_sha1(kck, 16, &input, 1, digest)) {
        return false;
    }
    memcpy(mic, digest, 16);
    memcpy(key->mic, mic, 16);
    return true;
}

static bool aes_key_wrap(const uint8_t kek[16], const uint8_t *plain,
                         size_t plain_len, uint8_t *wrapped)
{
    g_autoptr(QCryptoCipher) cipher = NULL;
    Error *error = NULL;
    uint64_t a = 0xa6a6a6a6a6a6a6a6ULL;
    uint64_t blocks[16];
    size_t count = plain_len / 8;
    size_t i;
    int round;

    if (!plain_len || plain_len % 8 || count > ARRAY_SIZE(blocks)) {
        return false;
    }
    cipher = qcrypto_cipher_new(
        QCRYPTO_CIPHER_ALGO_AES_128,
        QCRYPTO_CIPHER_MODE_ECB,
        kek,
        16,
        &error
    );
    if (!cipher) {
        error_report_err(error);
        return false;
    }
    for (i = 0; i < count; i++) {
        blocks[i] = get_be64(plain + i * 8);
    }
    for (round = 0; round < 6; round++) {
        for (i = 1; i <= count; i++) {
            uint8_t input[16];
            uint8_t output[16];
            uint64_t t = (uint64_t)count * round + i;

            put_be64(input, a);
            put_be64(input + 8, blocks[i - 1]);
            if (qcrypto_cipher_encrypt(
                    cipher, input, output, sizeof(input), &error) < 0) {
                error_report_err(error);
                return false;
            }
            a = get_be64(output) ^ t;
            blocks[i - 1] = get_be64(output + 8);
        }
    }
    put_be64(wrapped, a);
    for (i = 0; i < count; i++) {
        put_be64(wrapped + 8 + i * 8, blocks[i]);
    }
    return true;
}

static bool aes_block(QCryptoCipher *cipher,
                      const uint8_t input[16], uint8_t output[16])
{
    Error *error = NULL;

    if (qcrypto_cipher_encrypt(
            cipher, input, output, 16, &error) < 0) {
        error_report_err(error);
        return false;
    }
    return true;
}

static void xor_block(uint8_t output[16], const uint8_t input[16])
{
    int i;

    for (i = 0; i < 16; i++) {
        output[i] ^= input[i];
    }
}

static void ccmp_header_aad_nonce(const uint8_t *header,
                                  const uint8_t ccmp[8],
                                  uint8_t aad[22],
                                  uint8_t nonce[13])
{
    uint16_t fc = header[0] | ((uint16_t)header[1] << 8);
    uint16_t sequence = header[22] | ((uint16_t)header[23] << 8);

    fc &= ~0x0070;
    fc &= ~(BIT(11) | BIT(12) | BIT(13));
    fc |= BIT(14);
    aad[0] = fc;
    aad[1] = fc >> 8;
    memcpy(aad + 2, header + 4, 18);
    sequence &= 0x000f;
    aad[20] = sequence;
    aad[21] = sequence >> 8;

    nonce[0] = 0;
    memcpy(nonce + 1, header + 10, 6);
    nonce[7] = ccmp[7];
    nonce[8] = ccmp[6];
    nonce[9] = ccmp[5];
    nonce[10] = ccmp[4];
    nonce[11] = ccmp[1];
    nonce[12] = ccmp[0];
}

static bool aes_ccm_encrypt(const uint8_t key[16],
                            const uint8_t nonce[13],
                            const uint8_t *plain, size_t plain_len,
                            const uint8_t *aad, size_t aad_len,
                            uint8_t *crypt, uint8_t auth[8])
{
    g_autoptr(QCryptoCipher) cipher = NULL;
    Error *error = NULL;
    uint8_t b0[16] = { 0 };
    uint8_t aad_block[32] = { 0 };
    uint8_t counter[16] = { 0 };
    uint8_t x[16] = { 0 };
    uint8_t stream[16];
    size_t i;

    if (plain_len > 0xffff || aad_len > 30) {
        return false;
    }
    cipher = qcrypto_cipher_new(
        QCRYPTO_CIPHER_ALGO_AES_128,
        QCRYPTO_CIPHER_MODE_ECB,
        key,
        16,
        &error
    );
    if (!cipher) {
        error_report_err(error);
        return false;
    }

    b0[0] = 0x59;
    memcpy(b0 + 1, nonce, 13);
    put_be16(b0 + 14, plain_len);
    if (!aes_block(cipher, b0, x)) {
        return false;
    }

    aad_block[1] = aad_len;
    memcpy(aad_block + 2, aad, aad_len);
    xor_block(aad_block, x);
    if (!aes_block(cipher, aad_block, x)) {
        return false;
    }
    if (aad_len > 14) {
        xor_block(aad_block + 16, x);
        if (!aes_block(cipher, aad_block + 16, x)) {
            return false;
        }
    }

    for (i = 0; i < plain_len; i += 16) {
        uint8_t block[16] = { 0 };
        size_t copy_len = MIN((size_t)16, plain_len - i);

        memcpy(block, plain + i, copy_len);
        xor_block(block, x);
        if (!aes_block(cipher, block, x)) {
            return false;
        }
    }

    counter[0] = 0x01;
    memcpy(counter + 1, nonce, 13);
    for (i = 0; i < plain_len; i += 16) {
        size_t copy_len = MIN((size_t)16, plain_len - i);
        size_t j;

        put_be16(counter + 14, i / 16 + 1);
        if (!aes_block(cipher, counter, stream)) {
            return false;
        }
        for (j = 0; j < copy_len; j++) {
            crypt[i + j] = plain[i + j] ^ stream[j];
        }
    }
    put_be16(counter + 14, 0);
    if (!aes_block(cipher, counter, stream)) {
        return false;
    }
    for (i = 0; i < 8; i++) {
        auth[i] = x[i] ^ stream[i];
    }
    return true;
}

static bool aes_ccm_decrypt(const uint8_t key[16],
                            const uint8_t nonce[13],
                            const uint8_t *crypt, size_t crypt_len,
                            const uint8_t *aad, size_t aad_len,
                            const uint8_t auth[8], uint8_t *plain)
{
    g_autoptr(QCryptoCipher) cipher = NULL;
    Error *error = NULL;
    uint8_t b0[16] = { 0 };
    uint8_t aad_block[32] = { 0 };
    uint8_t counter[16] = { 0 };
    uint8_t x[16] = { 0 };
    uint8_t stream[16];
    uint8_t expected_auth[8];
    size_t i;

    if (crypt_len > 0xffff || aad_len > 30) {
        return false;
    }
    cipher = qcrypto_cipher_new(
        QCRYPTO_CIPHER_ALGO_AES_128,
        QCRYPTO_CIPHER_MODE_ECB,
        key,
        16,
        &error
    );
    if (!cipher) {
        error_report_err(error);
        return false;
    }

    counter[0] = 0x01;
    memcpy(counter + 1, nonce, 13);
    for (i = 0; i < crypt_len; i += 16) {
        size_t copy_len = MIN((size_t)16, crypt_len - i);
        size_t j;

        put_be16(counter + 14, i / 16 + 1);
        if (!aes_block(cipher, counter, stream)) {
            return false;
        }
        for (j = 0; j < copy_len; j++) {
            plain[i + j] = crypt[i + j] ^ stream[j];
        }
    }

    b0[0] = 0x59;
    memcpy(b0 + 1, nonce, 13);
    put_be16(b0 + 14, crypt_len);
    if (!aes_block(cipher, b0, x)) {
        return false;
    }

    aad_block[1] = aad_len;
    memcpy(aad_block + 2, aad, aad_len);
    xor_block(aad_block, x);
    if (!aes_block(cipher, aad_block, x)) {
        return false;
    }
    if (aad_len > 14) {
        xor_block(aad_block + 16, x);
        if (!aes_block(cipher, aad_block + 16, x)) {
            return false;
        }
    }

    for (i = 0; i < crypt_len; i += 16) {
        uint8_t block[16] = { 0 };
        size_t copy_len = MIN((size_t)16, crypt_len - i);

        memcpy(block, plain + i, copy_len);
        xor_block(block, x);
        if (!aes_block(cipher, block, x)) {
            return false;
        }
    }

    put_be16(counter + 14, 0);
    if (!aes_block(cipher, counter, stream)) {
        return false;
    }
    for (i = 0; i < sizeof(expected_auth); i++) {
        expected_auth[i] = x[i] ^ stream[i];
    }
    return !memcmp(auth, expected_auth, sizeof(expected_auth));
}

static bool ccmp_encrypt_data(Esp32WifiState *s,
                              struct mac80211_frame *frame,
                              bool group)
{
    const uint8_t *header = (const uint8_t *)frame;
    const uint8_t *tk = group ? s->gtk : s->ptk + 32;
    uint8_t plain[2316];
    uint8_t aad[22];
    uint8_t nonce[13];
    uint8_t *ccmp = frame->data_and_fcs;
    size_t plain_len = frame->frame_length - IEEE80211_HEADER_SIZE;
    uint64_t pn = ++s->ap_pn;

    if (!plain_len || plain_len > sizeof(plain) ||
        IEEE80211_HEADER_SIZE + 8 + plain_len + 8 > sizeof(*frame)) {
        return false;
    }
    memcpy(plain, frame->data_and_fcs, plain_len);
    ccmp[0] = pn;
    ccmp[1] = pn >> 8;
    ccmp[2] = 0;
    ccmp[3] = 0x20 | (group ? 0x40 : 0);
    ccmp[4] = pn >> 16;
    ccmp[5] = pn >> 24;
    ccmp[6] = pn >> 32;
    ccmp[7] = pn >> 40;

    ccmp_header_aad_nonce(header, ccmp, aad, nonce);

    if (!aes_ccm_encrypt(
            tk, nonce, plain, plain_len, aad, sizeof(aad),
            ccmp + 8, ccmp + 8 + plain_len)) {
        return false;
    }
    frame->frame_length = IEEE80211_HEADER_SIZE + 8 + plain_len + 8;
    frame->frame_control._flags |= BIT(4);
    wpa_trace(
        "CCMP downlink pn=%" PRIu64 " keyid=%u plain=%zu",
        pn, group ? 1 : 0, plain_len
    );
    return true;
}

bool Esp32_WLAN_prepare_s3_rx(Esp32WifiState *s,
                              struct mac80211_frame *frame)
{
    const uint8_t *header = (const uint8_t *)frame;
    const uint8_t *ccmp = frame->data_and_fcs;
    const uint8_t *tk;
    uint8_t aad[22];
    uint8_t nonce[13];
    uint8_t plain[2316];
    uint8_t ccmp_header[8];
    size_t encrypted_len;
    size_t plain_len;
    bool group;

    if (frame->frame_control.type != IEEE80211_TYPE_DATA ||
        !(frame->frame_control._flags & BIT(4))) {
        return true;
    }
    if (!s->wifi_secured || s->wpa_state != ESP32_WIFI_WPA_READY) {
        wpa_trace("drop protected RX before WPA2 ready");
        return false;
    }
    if (frame->frame_length < IEEE80211_HEADER_SIZE + 4 + 16) {
        wpa_trace("drop short protected RX length=%u", frame->frame_length);
        return false;
    }

    /*
     * insertCRC() appends a four-byte FCS after the CCMP envelope.  It is
     * transport bookkeeping for this model, not part of the authenticated
     * payload.
     */
    encrypted_len =
        frame->frame_length - IEEE80211_HEADER_SIZE - 4;
    plain_len = encrypted_len - 8 - 8;
    if (plain_len < 8 || plain_len > sizeof(plain)) {
        wpa_trace("drop invalid protected RX plain=%zu", plain_len);
        return false;
    }
    group = !!(ccmp[3] & 0x40);
    tk = group ? s->gtk : s->ptk + 32;
    ccmp_header_aad_nonce(header, ccmp, aad, nonce);
    if (!aes_ccm_decrypt(
            tk, nonce, ccmp + 8, plain_len, aad, sizeof(aad),
            ccmp + 8 + plain_len, plain)) {
        wpa_trace("drop protected RX: CCMP authentication failed");
        return false;
    }

    if (8 + plain_len + 12 > sizeof(frame->data_and_fcs)) {
        wpa_trace("drop protected RX: decrypted frame too large");
        return false;
    }
    memcpy(ccmp_header, ccmp, sizeof(ccmp_header));
    memcpy(frame->data_and_fcs, ccmp_header, sizeof(ccmp_header));
    memcpy(frame->data_and_fcs + sizeof(ccmp_header), plain, plain_len);
    wpa_trace(
        "CCMP RX decrypted pn=%02x%02x keyid=%u plain=%zu",
        ccmp[1], ccmp[0], group ? 1 : 0, plain_len
    );
    return true;
}

// channel 12, 13 and 14 aren't scanned with probe requests, but by listening to beacons
// likely because those channels aren't freely licensed in all countries
access_point_info access_points[]={
    {"Open Wifi",4,-40,{0x10,0x01,0x00,0xc4,0x0a,0x51}},
    {"myssid",1,-25,{0x10,0x01,0x00,0xc4,0x0a,0x50}},
    {"Zeus WPI",12,-25,{0x10,0x01,0x00,0xc4,0x0a,0x56}}
};

int nb_aps=sizeof(access_points)/sizeof(access_point_info);

static void Esp32_WLAN_beacon_timer(void *opaque)
{
    struct mac80211_frame *frame;
    Esp32WifiState *s = (Esp32WifiState *)opaque;

    if (!s->radio_enabled || s->wlan_closed) { return; }
    // only send a beacon if we are an access point
    if(s->ap_state!=Esp32_WLAN__STATE_STA_ASSOCIATED) {
        if (access_points[s->beacon_ap].channel==esp32_wifi_channel) {
            printf("QEMU: sending beacon for AP %s\n", access_points[s->beacon_ap].ssid);
            memcpy(s->ap_macaddr,access_points[s->beacon_ap].mac_address,6);
            frame = Esp32_WLAN_create_beacon_frame(
                s,
                &access_points[s->beacon_ap]
            );
            memcpy(frame->receiver_address, BROADCAST, 6);
            memcpy(frame->transmitter_address, s->ap_macaddr, 6);
            memcpy(frame->address_3, s->ap_macaddr, 6);
            Esp32_WLAN_init_ap_frame(s, frame);
            Esp32_WLAN_insert_frame(s, frame);
        }
        s->beacon_ap=(s->beacon_ap+1)%nb_aps;
    }
    timer_mod(s->beacon_timer, qemu_clock_get_ns(QEMU_CLOCK_REALTIME) + BEACON_TIME);
}

static void Esp32_WLAN_inject_timer(void *opaque)
{
    Esp32WifiState *s = (Esp32WifiState *)opaque;
    struct mac80211_frame *frame;

    if (!s->radio_enabled || s->wlan_closed) { return; }
    frame = s->inject_queue;
    if (frame) {
        // remove from queue
        s->inject_queue_size--;
        s->inject_queue = frame->next_frame;
        Esp32_sendFrame(s, (void *)frame, frame->frame_length,frame->signal_strength);
        free(frame);
    }
    if (s->inject_queue_size > 0) {
        // there are more packets... schedule
        // the timer for sending them as well
        timer_mod(s->inject_timer, qemu_clock_get_ns(QEMU_CLOCK_REALTIME) + INTER_FRAME_TIME);
    } else {
        // we wait until a new packet schedules
        // us again
        s->inject_timer_running = 0;
        qemu_flush_queued_packets(qemu_get_queue(s->nic));
    }

}

static void macprint(uint8_t *p, const char * name) {
    printf("%s: %02x:%02x:%02x:%02x:%02x:%02x\n",name, p[0],p[1],p[2],p[3],p[4],p[5]);
}

static void infoprint(struct mac80211_frame *frame) {
    if(DEBUG_DUMPFRAMES) {
        printf("Frame Info type=%d subtype=%d to_ds=%d from_ds=%d duration=%d frame_length=%d\n",frame->frame_control.type,frame->frame_control.sub_type, frame->frame_control.to_ds,frame->frame_control.from_ds, frame->duration_id, frame->frame_length);
        macprint(frame->receiver_address,   "receiver   ");
        macprint(frame->transmitter_address,"transmitter");
        macprint(frame->address_3,          "3rd address");
        uint8_t *b=(uint8_t *)frame;
        for(int i=0;i<frame->frame_length;i++) {
            if((i%16)==0) printf("\n%04x: ",i);
            printf("%02x ",b[i]);
        }
        printf("\n");
    }
}

void Esp32_WLAN_insert_frame(Esp32WifiState *s, struct mac80211_frame *frame)
{
    struct mac80211_frame *i_frame;

    insertCRC(frame);
    if(DEBUG) printf("QEMU: sent frame (qemu AP -> ESP32) type=%d subtype=%d\n",frame->frame_control.type,frame->frame_control.sub_type);
    infoprint(frame);
    s->inject_queue_size++;
    i_frame = s->inject_queue;
    if (!i_frame) {
        s->inject_queue = frame;
    } else {
        while (i_frame->next_frame) {
            i_frame = i_frame->next_frame;
        }
        i_frame->next_frame = frame;
    }

    if (!s->inject_timer_running) {
        // if the injection timer is not
        // running currently, let's schedule
        // one run...
        s->inject_timer_running = 1;
        timer_mod(s->inject_timer, qemu_clock_get_ns(QEMU_CLOCK_REALTIME) + INTER_FRAME_TIME);
    }

}

static _Bool Esp32_WLAN_can_receive(NetClientState *ncs)
{
    Esp32WifiState *s = qemu_get_nic_opaque(ncs);

    if (s->ap_state != Esp32_WLAN__STATE_ASSOCIATED &&
        s->ap_state != Esp32_WLAN__STATE_STA_ASSOCIATED &&
        s->ap_state != Esp32_WLAN__STATE_STA_DHCP) {
        // we are currently not connected
        // to the access point
        return 0;
    }
    if (s->inject_queue_size > Esp32_WLAN__MAX_INJECT_QUEUE_SIZE) {
        // overload, please give me some time...
        return 0;
    }

    return 1;
}

static ssize_t Esp32_WLAN_receive(NetClientState *ncs,
                                    const uint8_t *buf, size_t size)
{
    Esp32WifiState *s = qemu_get_nic_opaque(ncs);
    struct mac80211_frame *frame;
    if (!s->radio_enabled || s->wlan_closed || ncs->link_down) { return size; }
    if (!Esp32_WLAN_can_receive(ncs)) {
        // this should not happen, but in
        // case it does, let's simply drop
        // the packet
        return -1;
    }

    if (!s) {
        return -1;
    }
    /*
     * A 802.3 packet comes from the qemu network. The
     * access points turns it into a 802.11 frame and
     * forwards it to the wireless device
     */
    frame = Esp32_WLAN_create_data_packet(s, buf, size);
    if (frame) {
        /* send message to ESP32 AP */
        if(s->ap_state == Esp32_WLAN__STATE_STA_ASSOCIATED) {
            printf("QEMU: Esp32_WLAN_create_data_packet not yet implemented for STA!");
            frame->frame_control.to_ds = 1;
            frame->frame_control.from_ds = 0;
            memcpy(frame->receiver_address, s->ap_macaddr, 6); // ?
            // TODO implement setting all 3 802.11 MAC addresses
        }
        else { // send message to ESP32 station
            bool dhcp_reply =
                size >= 42 &&
                buf[12] == 0x08 && buf[13] == 0x00 &&
                buf[23] == 17 &&
                buf[34] == 0 && buf[35] == 67 &&
                buf[36] == 0 && buf[37] == 68;
            const uint8_t *receiver =
                dhcp_reply &&
                s->wifi_secured &&
                s->wpa_state == ESP32_WIFI_WPA_READY
                ? s->station_macaddr
                : &buf[0];

            frame->frame_control.to_ds = 0;
            frame->frame_control.from_ds = 1;
            memcpy(frame->receiver_address, receiver, 6);
            memcpy(frame->transmitter_address, s->associated_ap_macaddr, 6);
            memcpy(frame->address_3, &buf[6], 6); // source address
        }
        Esp32_WLAN_init_ap_frame(s, frame);
        if (s->wifi_secured && s->wpa_state == ESP32_WIFI_WPA_READY) {
            /*
             * The S3 station data path expects pairwise-key CCMP for the
             * current single-station AP model, including broadcast DHCP.
             * Keep this aligned with the validated esp-emu RX format.
             */
            wpa_add_ccmp_envelope(s, frame, false);
        }
        Esp32_WLAN_insert_frame(s, frame);
    }
    return size;
}
static void wlan_drop_inject_queue(Esp32WifiState *s)
{
    while (s->inject_queue) {
        struct mac80211_frame *frame = s->inject_queue;
        s->inject_queue = frame->next_frame;
        free(frame);
    }
    s->inject_queue_size = 0;
    s->inject_timer_running = 0;
    if (s->inject_timer) { timer_del(s->inject_timer); }
}

static void Esp32_WLAN_cleanup(NetClientState *ncs)
{
    Esp32WifiState *s = qemu_get_nic_opaque(ncs);
    if (s->wlan_closed) { return; }
    s->wlan_closed = true;
    s->radio_enabled = false;
    wlan_drop_inject_queue(s);
    if (s->beacon_timer) { timer_free(s->beacon_timer); s->beacon_timer = NULL; }
    if (s->inject_timer) { timer_free(s->inject_timer); s->inject_timer = NULL; }
}

static void wlan_get_radio(Object *obj, Visitor *v, const char *name,
                            void *opaque, Error **errp)
{
    Esp32WifiState *s = opaque;
    bool enabled = s->radio_enabled;
    visit_type_bool(v, name, &enabled, errp);
}

static void wlan_set_radio(Object *obj, Visitor *v, const char *name,
                            void *opaque, Error **errp)
{
    Esp32WifiState *s = opaque;
    bool enabled;
    if (!visit_type_bool(v, name, &enabled, errp)) { return; }
    if (s->wlan_closed) { error_setg(errp, "WiFi device is closed"); return; }
    if (enabled == s->radio_enabled) { return; }
    if (!enabled) {
        /* Deliver a real management frame through the guest RX DMA before
         * removing the AP, so the guest driver observes deauthentication. */
        if (s->dma_inlink_address && s->ap_state == Esp32_WLAN__STATE_ASSOCIATED) {
            struct mac80211_frame *frame = Esp32_WLAN_create_deauthentication();
            memcpy(frame->receiver_address, BROADCAST, 6);
            memcpy(frame->transmitter_address, s->ap_macaddr, 6);
            memcpy(frame->address_3, s->ap_macaddr, 6);
            Esp32_WLAN_init_ap_frame(s, frame);
            Esp32_sendFrame(s, frame, frame->frame_length, -10);
            free(frame);
        }
        timer_del(s->beacon_timer);
        wlan_drop_inject_queue(s);
    }
    s->radio_enabled = enabled;
    s->ap_state = Esp32_WLAN__STATE_NOT_AUTHENTICATED;
    s->wpa_state = ESP32_WIFI_WPA_IDLE;
    s->beacon_ap = 0;
    if (enabled) {
        timer_mod(s->beacon_timer, qemu_clock_get_ns(QEMU_CLOCK_REALTIME) + 1000000);
        qemu_flush_queued_packets(qemu_get_queue(s->nic));
    }
}


static NetClientInfo net_info = {
    .type = NET_CLIENT_DRIVER_NIC,
    .size = sizeof(NICState),
    .can_receive = Esp32_WLAN_can_receive,
    .receive = Esp32_WLAN_receive,
    .cleanup = Esp32_WLAN_cleanup,
};

static bool esp32_wlan_has_configured_mac(Esp32WifiState *s)
{
    static const MACAddr zero = { .a = { 0, 0, 0, 0, 0, 0 } };

    return memcmp(&s->conf.macaddr, &zero, sizeof(zero)) != 0;
}

void Esp32_WLAN_setup_ap(DeviceState *dev,Esp32WifiState *s) {
    s->radio_enabled = true;
    s->wlan_closed = false;
    object_property_add(OBJECT(dev), "radio-enabled", "bool",
                        wlan_get_radio, wlan_set_radio, NULL, s);
    const char *wifi_ssid = getenv("M5SW_WIFI_SSID");
    const char *wifi_password = getenv("M5SW_WIFI_PASSWORD");
    const char *wifi_auth = getenv("M5SW_WIFI_AUTH");


    s->ap_state = Esp32_WLAN__STATE_NOT_AUTHENTICATED;
    s->beacon_ap=0;
    pstrcpy(s->wifi_ssid, sizeof(s->wifi_ssid),
            wifi_ssid && *wifi_ssid ? wifi_ssid : "myssid");
    pstrcpy(s->wifi_password, sizeof(s->wifi_password),
            wifi_password ? wifi_password : "");
    s->wifi_secured = wifi_auth && !strcmp(wifi_auth, "wpa2-psk") &&
                      strlen(s->wifi_password) >= 8;
    s->wpa_state = ESP32_WIFI_WPA_IDLE;
    s->wpa_replay_counter = 0;
    s->ap_pn = 0;
    memset(s->station_macaddr, 0, sizeof(s->station_macaddr));
    memset(s->wpa_station_addr, 0, sizeof(s->wpa_station_addr));
    memset(s->anonce, 0, sizeof(s->anonce));
    memset(s->snonce, 0, sizeof(s->snonce));
    memset(s->ptk, 0, sizeof(s->ptk));
    memset(s->gtk, 0, sizeof(s->gtk));
    if (s->wifi_secured && !wpa_derive_pmk(s)) {
        error_report("failed to derive WPA2 PMK for %s", s->wifi_ssid);
        s->wifi_secured = false;
    }
    access_points[1].ssid = s->wifi_ssid;
    memcpy(s->ap_macaddr,(uint8_t[]){0x01,0x13,0x46,0xbf,0x31,0x50},sizeof(s->ap_macaddr));
    if (esp32_wlan_has_configured_mac(s)) {
        memcpy(s->macaddr, s->conf.macaddr.a, sizeof(s->macaddr));
    } else {
        memcpy(s->macaddr,(uint8_t[]){0x10,0x01,0x00,0xc4,0x0a,0x24},sizeof(s->macaddr));
    }

    s->inject_timer_running = 0;
    s->inject_sequence_number = 0;

    s->inject_queue = NULL;
    s->inject_queue_size = 0;

    s->beacon_timer = timer_new_ns(QEMU_CLOCK_REALTIME, Esp32_WLAN_beacon_timer, s);
    timer_mod(s->beacon_timer, qemu_clock_get_ns(QEMU_CLOCK_REALTIME)+100000000);

    // setup the timer but only schedule
    // it when necessary...
    s->inject_timer = timer_new_ns(QEMU_CLOCK_REALTIME, Esp32_WLAN_inject_timer, s);

    s->nic = qemu_new_nic(&net_info, &s->conf,
                          object_get_typename(OBJECT(s)), dev->id,
                          &s->reentrancy_guard, s);
    qemu_format_nic_info_str(qemu_get_queue(s->nic), s->macaddr);
}

static void send_single_frame(Esp32WifiState *s, struct mac80211_frame *frame, struct mac80211_frame *reply) {
    reply->sequence_control.sequence_number = s->inject_sequence_number++ +0x730;
    reply->signal_strength=-10;

    if(frame) {
        memcpy(reply->receiver_address, frame->transmitter_address, 6);
        memcpy(reply->transmitter_address, s->macaddr, 6);
        memcpy(reply->address_3, frame->transmitter_address, 6);
    }

    Esp32_WLAN_insert_frame(s, reply);
}

static void wpa_add_ccmp_envelope(Esp32WifiState *s,
                                  struct mac80211_frame *frame,
                                  bool group)
{
    if (!ccmp_encrypt_data(s, frame, group)) {
        wpa_trace("CCMP downlink encryption failed");
    }
}

static struct mac80211_frame *wpa_create_eapol_frame(
    Esp32WifiState *s,
    const struct mac80211_frame *request,
    uint16_t key_info,
    const uint8_t *nonce,
    const uint8_t *key_data,
    size_t key_data_len,
    bool include_mic)
{
    struct mac80211_frame *frame = g_malloc0(sizeof(*frame));
    uint8_t *eapol = frame->data_and_fcs + 8;
    eapol_header *header = (eapol_header *)eapol;
    eapol_key *key = (eapol_key *)(eapol + sizeof(*header));
    size_t eapol_len = sizeof(*header) + sizeof(*key) + key_data_len;

    frame->frame_control.type = IEEE80211_TYPE_DATA;
    frame->frame_control.sub_type = IEEE80211_TYPE_DATA_SUBTYPE_DATA;
    frame->frame_control.from_ds = 1;
    frame->duration_id = 44;
    memcpy(
        frame->receiver_address,
        request ? request->transmitter_address : s->station_macaddr,
        6
    );
    memcpy(frame->transmitter_address, s->ap_macaddr, 6);
    memcpy(frame->address_3, s->ap_macaddr, 6);
    memcpy(
        frame->data_and_fcs,
        (uint8_t[]){ 0xaa, 0xaa, 0x03, 0x00, 0x00, 0x00, 0x88, 0x8e },
        8
    );
    header->version = EAPOL_VERSION;
    header->type = EAPOL_TYPE_KEY;
    put_be16((uint8_t *)&header->length, eapol_len - sizeof(*header));
    key->descriptor_type = 2;
    put_be16(key->key_info, key_info);
    put_be16(key->key_length, 16);
    s->wpa_replay_counter++;
    put_be64(key->replay_counter, s->wpa_replay_counter);
    if (nonce) {
        memcpy(key->nonce, nonce, 32);
    }
    put_be16(key->key_data_length, key_data_len);
    if (key_data_len) {
        memcpy(eapol + sizeof(*header) + sizeof(*key),
               key_data, key_data_len);
    }
    if (include_mic) {
        uint8_t mic[16];

        if (!wpa_eapol_mic(s->ptk, key, eapol, eapol_len, mic)) {
            g_free(frame);
            return NULL;
        }
    }
    frame->frame_length = IEEE80211_HEADER_SIZE + 8 + eapol_len;
    Esp32_WLAN_init_ap_frame(s, frame);
    return frame;
}

static bool wpa_send_message1(Esp32WifiState *s)
{
    struct mac80211_frame *frame = wpa_create_eapol_frame(
        s,
        NULL,
        WPA_KEY_INFO_HMAC_SHA1_AES |
        WPA_KEY_INFO_KEY_TYPE |
        WPA_KEY_INFO_ACK,
        s->anonce,
        NULL,
        0,
        false
    );

    if (!frame) {
        return false;
    }
    wpa_trace(
        "EAPOL 1/4 sent replay=%" PRIu64 " station=%02x:%02x:%02x:%02x:%02x:%02x",
        s->wpa_replay_counter,
        s->station_macaddr[0], s->station_macaddr[1],
        s->station_macaddr[2], s->station_macaddr[3],
        s->station_macaddr[4], s->station_macaddr[5]
    );
    Esp32_WLAN_insert_frame(s, frame);
    return true;
}

static bool wpa_send_message3(Esp32WifiState *s)
{
    uint8_t plain[48] = { 0 };
    uint8_t wrapped[56];
    uint8_t *position = plain;
    struct mac80211_frame *frame;

    memcpy(position, wpa_rsn_ie, sizeof(wpa_rsn_ie));
    position += sizeof(wpa_rsn_ie);
    *position++ = 0xdd;
    *position++ = 0x16;
    memcpy(position, (uint8_t[]){ 0x00, 0x0f, 0xac, 0x01 }, 4);
    position += 4;
    *position++ = 1;
    *position++ = 0;
    memcpy(position, s->gtk, sizeof(s->gtk));
    position += sizeof(s->gtk);
    *position++ = 0xdd;

    if (!aes_key_wrap(s->ptk + 16, plain, sizeof(plain), wrapped)) {
        return false;
    }
    frame = wpa_create_eapol_frame(
        s,
        NULL,
        WPA_KEY_INFO_HMAC_SHA1_AES |
        WPA_KEY_INFO_KEY_TYPE |
        WPA_KEY_INFO_INSTALL |
        WPA_KEY_INFO_ACK |
        WPA_KEY_INFO_MIC |
        WPA_KEY_INFO_SECURE |
        WPA_KEY_INFO_ENCR_KEY_DATA,
        s->anonce,
        wrapped,
        sizeof(wrapped),
        true
    );
    if (!frame) {
        return false;
    }
    wpa_trace(
        "EAPOL 3/4 sent replay=%" PRIu64 " key_data=%zu",
        s->wpa_replay_counter,
        sizeof(wrapped)
    );
    Esp32_WLAN_insert_frame(s, frame);
    return true;
}

static bool wpa_send_deauth(Esp32WifiState *s, uint16_t reason)
{
    struct mac80211_frame *frame = g_malloc0(sizeof(*frame));

    frame->frame_control.type = IEEE80211_TYPE_MGT;
    frame->frame_control.sub_type = IEEE80211_TYPE_MGT_SUBTYPE_DEAUTHENTICATION;
    memcpy(frame->receiver_address, s->station_macaddr, 6);
    memcpy(frame->transmitter_address, s->ap_macaddr, 6);
    memcpy(frame->address_3, s->ap_macaddr, 6);
    frame->data_and_fcs[0] = reason;
    frame->data_and_fcs[1] = reason >> 8;
    frame->frame_length = IEEE80211_HEADER_SIZE + 2;
    Esp32_WLAN_init_ap_frame(s, frame);
    wpa_trace("deauthenticate station reason=%u", reason);
    Esp32_WLAN_insert_frame(s, frame);
    s->wpa_state = ESP32_WIFI_WPA_IDLE;
    return true;
}

static bool wpa_handle_eapol(Esp32WifiState *s,
                             struct mac80211_frame *frame)
{
    uint8_t *eapol;
    eapol_header *header;
    eapol_key *key;
    uint16_t key_info;
    uint16_t key_data_length;
    uint16_t eapol_length;
    uint64_t replay;
    uint8_t received_mic[16];

    if (frame->frame_length < IEEE80211_HEADER_SIZE + 8 + sizeof(*header) ||
        memcmp(frame->data_and_fcs, (uint8_t[]){
            0xaa, 0xaa, 0x03, 0x00, 0x00, 0x00, 0x88, 0x8e }, 8)) {
        return false;
    }
    eapol = frame->data_and_fcs + 8;
    header = (eapol_header *)eapol;
    if (header->version != EAPOL_VERSION || header->type != EAPOL_TYPE_KEY) {
        return false;
    }
    eapol_length = sizeof(*header) + get_be16((uint8_t *)&header->length);
    if (eapol_length < sizeof(*header) + sizeof(*key) ||
        eapol_length > frame->frame_length - IEEE80211_HEADER_SIZE - 8) {
        wpa_trace("drop malformed EAPOL length=%u", eapol_length);
        return true;
    }
    key = (eapol_key *)(eapol + sizeof(*header));
    if (key->descriptor_type != 2) {
        return true;
    }
    key_info = get_be16(key->key_info);
    key_data_length = get_be16(key->key_data_length);
    replay = get_be64(key->replay_counter);
    if (!(key_info & WPA_KEY_INFO_KEY_TYPE) ||
        !(key_info & WPA_KEY_INFO_MIC) ||
        (key_info & WPA_KEY_INFO_ACK) ||
        sizeof(*header) + sizeof(*key) + key_data_length > eapol_length) {
        wpa_trace(
            "drop unexpected EAPOL key_info=%04x replay=%" PRIu64,
            key_info, replay
        );
        return true;
    }
    wpa_trace(
        "EAPOL received key_info=%04x replay=%" PRIu64
        " state=%u data=%u",
        key_info, replay, s->wpa_state, key_data_length
    );

    if (s->wpa_state == ESP32_WIFI_WPA_WAIT_M2) {
        uint8_t expected_mic[16];

        if (replay != s->wpa_replay_counter) {
            wpa_trace("EAPOL 2/4 replay mismatch");
            return true;
        }
        memcpy(s->snonce, key->nonce, sizeof(s->snonce));
        if (!wpa_derive_ptk(s)) {
            wpa_trace("EAPOL 2/4 PTK derivation failed");
            return true;
        }
        memcpy(received_mic, key->mic, sizeof(received_mic));
        if (!wpa_eapol_mic(
                s->ptk, key, eapol, eapol_length, expected_mic) ||
            memcmp(received_mic, expected_mic, sizeof(received_mic))) {
            wpa_trace("EAPOL 2/4 MIC mismatch");
            wpa_send_deauth(s, 15);
            return true;
        }
        wpa_trace("EAPOL 2/4 verified");
        s->wpa_state = ESP32_WIFI_WPA_WAIT_M4;
        if (!wpa_send_message3(s)) {
            wpa_trace("EAPOL 3/4 construction failed");
            wpa_send_deauth(s, 15);
        }
        return true;
    }

    if (s->wpa_state == ESP32_WIFI_WPA_WAIT_M4) {
        uint8_t expected_mic[16];

        if (replay != s->wpa_replay_counter) {
            wpa_trace("EAPOL 4/4 replay mismatch");
            return true;
        }
        memcpy(received_mic, key->mic, sizeof(received_mic));
        if (!wpa_eapol_mic(
                s->ptk, key, eapol, eapol_length, expected_mic) ||
            memcmp(received_mic, expected_mic, sizeof(received_mic))) {
            wpa_trace("EAPOL 4/4 MIC mismatch");
            wpa_send_deauth(s, 15);
            return true;
        }
        wpa_trace("EAPOL 4/4 verified; WPA2-PSK ready");
        s->wpa_state = ESP32_WIFI_WPA_READY;
        return true;
    }

    return true;
}

void Esp32_WLAN_handle_frame(Esp32WifiState *s, struct mac80211_frame *frame)
{
    if (!s->radio_enabled || s->wlan_closed ||
        (s->nic && qemu_get_queue(s->nic)->link_down)) { return; }
    struct mac80211_frame *reply = NULL;
    static access_point_info dummy_ap={0};
    bool start_wpa = false;
    char ssid[64];
    unsigned long ethernet_frame_size;
    unsigned char ethernet_frame[1518] = {0};
    if(DEBUG)
        printf("QEMU: received frame (esp32 -> qemu) type=%d subtype=%d chan=%d to_ds=%d from_ds=%d state=%d\n",frame->frame_control.type, frame->frame_control.sub_type, esp32_wifi_channel, frame->frame_control.to_ds, frame->frame_control.from_ds, s->ap_state);
    infoprint(frame);
    access_point_info *ap_info=0;
    for (int i=0;i<nb_aps;i++) {
        if (access_points[i].channel == esp32_wifi_channel) {
            if (DEBUG) printf("QEMU: matching ap found: %s\n", access_points[i].ssid);
            ap_info=&access_points[i];
        }
    }

    if(frame->frame_control.type == IEEE80211_TYPE_MGT) {
        switch(frame->frame_control.sub_type) {
            case IEEE80211_TYPE_MGT_SUBTYPE_BEACON:
                if(s->ap_state==Esp32_WLAN__STATE_NOT_AUTHENTICATED || s->ap_state==Esp32_WLAN__STATE_AUTHENTICATED) {
                    strncpy(ssid,(char *)frame->data_and_fcs+14,frame->data_and_fcs[13]);
                    if(DEBUG) printf("QEMU: beacon from %s\n",ssid);
                    dummy_ap.ssid=ssid;
                    s->ap_state=Esp32_WLAN__STATE_STA_NOT_AUTHENTICATED;
                    send_single_frame(s,frame,Esp32_WLAN_create_probe_request(&dummy_ap));
                }
                break;
            case IEEE80211_TYPE_MGT_SUBTYPE_PROBE_RESP:
                ap_info=&dummy_ap;
                strncpy(ssid,(char *)frame->data_and_fcs+14,frame->data_and_fcs[13]);
                if(DEBUG) printf("QEMU: probe resp from %s\n",ssid);
                dummy_ap.ssid=ssid;
                s->ap_state=Esp32_WLAN__STATE_STA_NOT_AUTHENTICATED;
                send_single_frame(s,frame,Esp32_WLAN_create_deauthentication());
                send_single_frame(s,frame,Esp32_WLAN_create_authentication_request());
                break;
            case IEEE80211_TYPE_MGT_SUBTYPE_ASSOCIATION_RESP:
                if(DEBUG) printf("QEMU: assoc resp\n");
                mac80211_frame *frame1=Esp32_WLAN_create_dhcp_discover();
                memcpy(frame1->address_3,BROADCAST,6);
                memcpy(frame1->transmitter_address,frame->receiver_address,6);
                memcpy(frame1->receiver_address,frame->transmitter_address,6);
                send_single_frame(s,0,frame1);
                s->ap_state=Esp32_WLAN__STATE_STA_DHCP;
                break;
            case IEEE80211_TYPE_MGT_SUBTYPE_DISASSOCIATION:
                DEBUG_PRINT_AP(("QEMU: Received disassociation!\n"));
                send_single_frame(s,frame,Esp32_WLAN_create_disassociation());
                if (s->ap_state == Esp32_WLAN__STATE_ASSOCIATED || s->ap_state == Esp32_WLAN__STATE_STA_ASSOCIATED) {
                    s->ap_state = Esp32_WLAN__STATE_AUTHENTICATED;
                }
                break;
            case IEEE80211_TYPE_MGT_SUBTYPE_DEAUTHENTICATION:
                DEBUG_PRINT_AP(("QEMU: Received deauthentication!\n"));
                //reply = Esp32_WLAN_create_authentication_response(ap_info);
                if (s->ap_state == Esp32_WLAN__STATE_AUTHENTICATED) {
                    s->ap_state = Esp32_WLAN__STATE_NOT_AUTHENTICATED;
                }
                break;
            case IEEE80211_TYPE_MGT_SUBTYPE_AUTHENTICATION:
                if(frame->data_and_fcs[2]==2) { // response
                    DEBUG_PRINT_AP(("QEMU: Received authentication response!\n"));
                    send_single_frame(s,frame,Esp32_WLAN_create_association_request(&dummy_ap));
                }
                break;
        }
        if(ap_info) {
            memcpy(s->ap_macaddr, ap_info->mac_address, 6);
            switch(frame->frame_control.sub_type) {
                case IEEE80211_TYPE_MGT_SUBTYPE_PROBE_REQ:
                    DEBUG_PRINT_AP(("QEMU: Received probe request!\n"));
                    reply = Esp32_WLAN_create_probe_response(s, ap_info);
                    break;
                case IEEE80211_TYPE_MGT_SUBTYPE_AUTHENTICATION:
                    if(frame->data_and_fcs[2]==1) { // request
                        DEBUG_PRINT_AP(("QEMU: Received authentication request!\n"));
                        reply = Esp32_WLAN_create_authentication_response(ap_info);
                        if (s->ap_state == Esp32_WLAN__STATE_NOT_AUTHENTICATED) {
                            s->ap_state = Esp32_WLAN__STATE_AUTHENTICATED;
                        }
                    }
                break;
                case IEEE80211_TYPE_MGT_SUBTYPE_ASSOCIATION_REQ:
                    DEBUG_PRINT_AP(("QEMU: Received association request!\n"));
                    reply = Esp32_WLAN_create_association_response(s, ap_info);
                    if (s->ap_state == Esp32_WLAN__STATE_AUTHENTICATED) {
                        s->ap_state = Esp32_WLAN__STATE_ASSOCIATED;
                        memcpy(s->associated_ap_macaddr,s->ap_macaddr,6);
                        if (s->wifi_secured) {
                            memcpy(
                                s->station_macaddr,
                                frame->transmitter_address,
                                sizeof(s->station_macaddr)
                            );
                            memcpy(
                                s->wpa_station_addr,
                                frame->transmitter_address,
                                sizeof(s->wpa_station_addr)
                            );
                            qemu_guest_getrandom_nofail(
                                s->anonce, sizeof(s->anonce)
                            );
                            qemu_guest_getrandom_nofail(
                                s->gtk, sizeof(s->gtk)
                            );
                            memset(s->snonce, 0, sizeof(s->snonce));
                            memset(s->ptk, 0, sizeof(s->ptk));
                            s->wpa_replay_counter = 0;
                            s->wpa_state = ESP32_WIFI_WPA_WAIT_M2;
                            start_wpa = true;
                        }
                    }
                    break;
            }
            if (reply) {
                reply->signal_strength=ap_info->sigstrength;
                memcpy(reply->receiver_address, frame->transmitter_address, 6);
                memcpy(reply->transmitter_address, s->ap_macaddr, 6);
                memcpy(reply->address_3, s->ap_macaddr, 6);
                Esp32_WLAN_init_ap_frame(s, reply);
                Esp32_WLAN_insert_frame(s, reply);
                if (start_wpa && !wpa_send_message1(s)) {
                    wpa_trace("EAPOL 1/4 construction failed");
                    wpa_send_deauth(s, 15);
                }
            }
        }
    }
    if (frame->frame_control.type == IEEE80211_TYPE_DATA &&
        wpa_handle_eapol(s, frame)) {
        return;
    }
    if ((frame->frame_control.type == IEEE80211_TYPE_DATA) &&
        (frame->frame_control.sub_type == IEEE80211_TYPE_DATA_SUBTYPE_DATA)) {
        if(s->ap_state == Esp32_WLAN__STATE_STA_DHCP) {
            printf("QEMU: STA DHCP not implemented yet\n");
            dhcp_request_t *req=(dhcp_request_t *)&frame->data_and_fcs[8];
            // check for a dhcp offer
            if(req->dhcp.bp_options[0]==0x35 && req->dhcp.bp_options[2]==0x2) {
                mac80211_frame *frame1=Esp32_WLAN_create_dhcp_request(req->dhcp.yiaddr);
                memcpy(frame1->address_3,BROADCAST,6);
                memcpy(frame1->transmitter_address,s->macaddr,6);
                memcpy(frame1->receiver_address,frame->transmitter_address,6);
                send_single_frame(s,0,frame1);
                memcpy(s->ap_macaddr,(uint8_t[]){0x10,0x01,0x00,0xc4,0x0a,0x25},sizeof(s->ap_macaddr));
                if (!esp32_wlan_has_configured_mac(s)) {
                    memcpy(s->macaddr,(uint8_t[]){0x10,0x01,0x00,0xc4,0x0a,0x24},sizeof(s->macaddr));
                }
                memcpy(s->associated_ap_macaddr,s->ap_macaddr,sizeof(s->ap_macaddr));
                s->ap_state=Esp32_WLAN__STATE_STA_ASSOCIATED;
            }
        } else if (s->ap_state == Esp32_WLAN__STATE_ASSOCIATED) {
            size_t payload_offset = 0;

            // ESP32 to QEMU
            /*
            * The access point uses the 802.11 frame
            * and sends a 802.3 frame into the network...
            * This packet is then understandable by
            * qemu-slirp
            *
            * If we ever want the access point to offer
            * some services, it can be added here!!
            */
            /*
             * The ESP WiFi driver presents protected data to the MAC as a
             * hardware-CCMP envelope: 8-byte PN/key header followed by the
             * already decrypted LLC payload.  Strip that hardware boundary
             * before converting to an Ethernet frame for the host stack.
             */
            if (s->wifi_secured &&
                s->wpa_state == ESP32_WIFI_WPA_READY &&
                frame->frame_length > IEEE80211_HEADER_SIZE + 16 &&
                memcmp(frame->data_and_fcs, (uint8_t[]){
                    0xaa, 0xaa, 0x03, 0x00, 0x00, 0x00 }, 6) &&
                !memcmp(frame->data_and_fcs + 8, (uint8_t[]){
                    0xaa, 0xaa, 0x03, 0x00, 0x00, 0x00 }, 6)) {
                payload_offset = 8;
            }

            // ethernet header type
            ethernet_frame[12] = frame->data_and_fcs[payload_offset + 6];
            ethernet_frame[13] = frame->data_and_fcs[payload_offset + 7];

            // the originator the packet is the station who sent the frame
            memcpy(&ethernet_frame[6], frame->transmitter_address, 6);

            // in case of to_ds = 1 and from_ds = 0, the third address is the destination address
            memcpy(&ethernet_frame[0], frame->address_3, 6);

            ethernet_frame_size =
                frame->frame_length - 22 - payload_offset;

            // limit data to max length of ethernet frame
            if (ethernet_frame_size > (sizeof(ethernet_frame) - 14)) {
                ethernet_frame_size = (sizeof(ethernet_frame) - 14);
            }

            // set ethernet data
            memcpy(
                &ethernet_frame[14],
                &frame->data_and_fcs[payload_offset + 8],
                ethernet_frame_size
            );

            // send frame
            qemu_send_packet(qemu_get_queue(s->nic), ethernet_frame,
                             ethernet_frame_size);
        } else if (s->ap_state == Esp32_WLAN__STATE_STA_ASSOCIATED) {
            printf("QEMU: STA DATA, NOT IMPLEMENTED YET\n");
        }
    }
}
