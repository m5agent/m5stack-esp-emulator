/*
 * External Grove control Units.  SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Protocol sources: m5stack/uiflow-micropython unit/{joystick,encoder,
 * encoder8,cardkb,rfid}.py and driver/mfrc522, read 2026-10-26.  CardKB
 * v1.1 key tables: official Unit_CardKB_v1_1_User_Manual_EN.pdf.  See the
 * repository's platform/units/catalog.json for source URLs and SHA-256.
 *
 * These are controller-visible transaction models, not RF/electrical models.
 * RFID2 preserves the WS1850S product vs MFRC522 schematic distinction; its
 * command interface here is explicitly MFRC522-compatible. Card memory/key
 * material is a deterministic synthetic MIFARE Classic 1 KiB fixture only.
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qapi/qmp/qlist.h"
#include "qapi/qmp/qnum.h"
#include "qapi/qmp/qbool.h"
#include "hw/i2c/i2c.h"
#include "hw/qdev-properties.h"
#include "m5_unit_runtime.h"

#define TYPE_M5_UNIT_CONTROL "m5-unit-i2c-control"
#define CARD_KEYS 50
#define KEY_FIFO_SIZE 64
#define RFID_FIFO_SIZE 64

bool m5_unit_controls_supported(const char *unit_id);
void m5_unit_controls_realize(M5Unit *unit, Error **errp);

typedef enum {
    CONTROL_JOYSTICK, CONTROL_ENCODER, CONTROL_ENCODER8,
    CONTROL_CARDKB, CONTROL_RFID2,
} ControlKind;

typedef struct M5UnitControl {
    I2CSlave parent_obj;
    M5Unit *unit;
    ControlKind kind;
    uint8_t pointer, write_base, regs[256], read_snapshot[256];
    unsigned write_pos, read_pos;
    bool reading, memory_request;
    uint8_t joystick[3];
    int32_t counter[8], increments[8];
    bool pressed[8], switch_on;
    uint32_t leds[9];
    uint8_t led_write[4];
    bool keys[CARD_KEYS];
    uint8_t key_fifo[KEY_FIFO_SIZE];
    unsigned key_head, key_count;
    uint8_t modifier_mode;
    int64_t modifier_at;
    uint64_t key_overflows;
    bool card_present, card_halted, card_ready, card_selected;
    uint8_t uid[10], uid_len, cascade_level, card_memory[1024];
    int auth_sector, pending_write;
    uint8_t rfid_fifo[RFID_FIFO_SIZE], rfid_len;
    uint64_t card_reads, card_writes, command_errors;
} M5UnitControl;
OBJECT_DECLARE_SIMPLE_TYPE(M5UnitControl, M5_UNIT_CONTROL)

/* Order follows the frozen public CardKB shell, not a guessed GPIO matrix. */
static const char *const key_ids[CARD_KEYS] = {
    "esc", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "backspace",
    "tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "fn",
    "shift", "a", "s", "d", "f", "g", "h", "j", "k", "l", "enter",
    "sym", "z", "x", "c", "v", "b", "n", "m", "comma", "period", "space",
    "up", "left", "right", "down",
};
static const uint8_t key_normal[CARD_KEYS] = {
    0x1b, '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 8,
    9, 'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 0,
    0, 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 13,
    0, 'z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', ' ',
    0xb5, 0xb4, 0xb7, 0xb6,
};
static const uint8_t key_symbol[CARD_KEYS] = {
    0x1b, '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', 8,
    9, '{', '}', '[', ']', '/', '\\', '|', '~', '\'', '"', 0,
    0, ';', ':', '`', '+', '-', '_', '=', '?', 0, 13,
    0, 0, 0, 0, 0, 0, 0, 0, '<', '>', ' ',
    0xb5, 0xb4, 0xb7, 0xb6,
};
static const uint8_t key_function[CARD_KEYS] = {
    0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b,
    0x8c, 0x8d, 0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0,
    0, 0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f, 0xa0, 0xa1, 0xa2, 0xa3,
    0, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xad, 0xae, 0xaf,
    0x99, 0x98, 0xa5, 0xa4,
};

static void input_changed(M5UnitControl *s) { s->unit->input_events++; }
static void output_changed(M5UnitControl *s) { s->unit->output_transitions++; }

static void key_push(M5UnitControl *s, uint8_t value)
{
    if (!value) { return; }
    if (s->key_count == KEY_FIFO_SIZE) { s->key_overflows++; return; }
    s->key_fifo[(s->key_head + s->key_count) % KEY_FIFO_SIZE] = value;
    s->key_count++;
}

static void key_press(M5UnitControl *s, unsigned index)
{
    unsigned family = index == 24 ? 1 : index == 35 ? 3 : index == 23 ? 5 : 0;
    if (family) {
        int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        /* The older official MCU source uses a 200 ms double-click window.
         * Manual confirms one-shot/lock, not an exact timing tolerance. */
        if (s->modifier_mode == family && now - s->modifier_at <= 200000000) {
            s->modifier_mode = family + 1;
        } else if (s->modifier_mode == family || s->modifier_mode == family + 1) {
            s->modifier_mode = 0;
        } else { s->modifier_mode = family; }
        s->modifier_at = now;
        output_changed(s);
        return;
    }
    uint8_t value = key_normal[index];
    if (s->modifier_mode == 1 || s->modifier_mode == 2) {
        if (value >= 'a' && value <= 'z') { value -= 'a' - 'A'; }
    } else if (s->modifier_mode == 3 || s->modifier_mode == 4) {
        value = key_symbol[index];
    } else if (s->modifier_mode == 5 || s->modifier_mode == 6) {
        value = key_function[index];
    }
    key_push(s, value);
    if (value && (s->modifier_mode & 1)) {
        s->modifier_mode = 0;
        output_changed(s);
    }
}

static uint16_t crc_a(const uint8_t *data, unsigned len)
{
    uint16_t crc = 0x6363;
    for (unsigned i = 0; i < len; i++) {
        uint8_t x = data[i] ^ (crc & 0xff);
        x ^= x << 4;
        crc = (crc >> 8) ^ ((uint16_t)x << 8) ^ ((uint16_t)x << 3) ^ (x >> 4);
    }
    return crc;
}

static void rfid_reset(M5UnitControl *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x11] = 0x3f;
    s->regs[0x26] = 0x48;
    /* 0x92 identifies the implemented compatibility interface, not WS1850S silicon. */
    s->regs[0x37] = 0x92;
    s->rfid_len = 0;
    s->auth_sector = -1;
    s->pending_write = -1;
    s->cascade_level = 0;
    s->card_ready = s->card_selected = s->card_halted = false;
}

static void rfid_reply(M5UnitControl *s, const uint8_t *bytes,
                       unsigned length, unsigned valid_bits)
{
    assert(length <= RFID_FIFO_SIZE);
    if (length) { memcpy(s->rfid_fifo, bytes, length); }
    s->rfid_len = length;
    s->regs[0x0c] = (s->regs[0x0c] & ~7) | (valid_bits & 7);
    s->regs[0x06] = 0;
    s->regs[0x04] = 0x30; /* RxIRq + IdleIRq */
    s->regs[0x0d] &= ~0x80;
}

static void rfid_timeout(M5UnitControl *s)
{
    s->rfid_len = 0;
    s->regs[0x06] = 0;
    s->regs[0x04] = 1; /* TimerIRq: there was no PICC response */
    s->regs[0x0d] &= ~0x80;
}

static void rfid_nack(M5UnitControl *s)
{
    static const uint8_t nack = 0x04;
    s->command_errors++;
    rfid_reply(s, &nack, 1, 4);
}

static bool rfid_crc_valid(const uint8_t *data, unsigned length)
{
    if (length < 3) { return false; }
    uint16_t crc = crc_a(data, length - 2);
    return data[length - 2] == (crc & 0xff) && data[length - 1] == (crc >> 8);
}

static bool rfid_authorized(M5UnitControl *s, unsigned block)
{
    return s->card_selected && (s->regs[0x08] & 8) &&
           block < 64 && s->auth_sector == block / 4;
}

static void rfid_transceive(M5UnitControl *s)
{
    uint8_t tx[RFID_FIFO_SIZE], reply[18], uid_block[5];
    unsigned n = s->rfid_len;
    memcpy(tx, s->rfid_fifo, n);
    s->rfid_len = 0;
    if (!s->card_present || (s->regs[0x14] & 3) != 3 || !n) {
        rfid_timeout(s); return;
    }
    if ((tx[0] == 0x26 || tx[0] == 0x52) && n == 1 && (s->regs[0x0d] & 7) == 7) {
        if (s->card_halted && tx[0] == 0x26) { rfid_timeout(s); return; }
        s->card_halted = false; s->card_ready = true; s->card_selected = false;
        s->cascade_level = 0;
        s->auth_sector = -1; s->regs[0x08] &= ~8;
        reply[0] = 0x04 | (((s->uid_len - 4) / 3) << 6); reply[1] = 0;
        rfid_reply(s, reply, 2, 0); return;
    }
    if (s->card_halted) { rfid_timeout(s); return; }
    if ((tx[0] == 0x93 || tx[0] == 0x95 || tx[0] == 0x97) && n >= 2) {
        unsigned level = (tx[0] - 0x93) / 2, start = level * 3;
        unsigned levels = (s->uid_len - 4) / 3 + 1;
        if (!s->card_ready || level >= levels || level != s->cascade_level) {
            rfid_timeout(s); return;
        }
        bool more = s->uid_len - start > 4;
        if (more) { uid_block[0] = 0x88; memcpy(uid_block + 1, s->uid + start, 3); }
        else { memcpy(uid_block, s->uid + start, 4); }
        uid_block[4] = uid_block[0] ^ uid_block[1] ^ uid_block[2] ^ uid_block[3];
        if (tx[1] == 0x20 && n == 2) { rfid_reply(s, uid_block, 5, 0); return; }
        if (tx[1] == 0x70 && n == 9 && !memcmp(tx + 2, uid_block, 5) && rfid_crc_valid(tx, n)) {
            reply[0] = more ? 0x04 : 0x08;
            uint16_t crc = crc_a(reply, 1); reply[1] = crc; reply[2] = crc >> 8;
            if (!more) { s->card_selected = true; }
            else { s->cascade_level++; }
            rfid_reply(s, reply, 3, 0); return;
        }
        rfid_nack(s); return;
    }
    if (!rfid_crc_valid(tx, n)) {
        s->pending_write = -1;
        s->command_errors++; s->regs[0x06] = 0x04; s->regs[0x04] = 0x01;
        s->regs[0x0d] &= ~0x80; return;
    }
    if (s->pending_write >= 0) {
        unsigned block = s->pending_write;
        s->pending_write = -1;
        if (n != 18 || !rfid_authorized(s, block) || block == 0) { rfid_nack(s); return; }
        bool changed = memcmp(s->card_memory + block * 16, tx, 16) != 0;
        memcpy(s->card_memory + block * 16, tx, 16); s->card_writes++;
        if (changed) { output_changed(s); }
        reply[0] = 0x0a; rfid_reply(s, reply, 1, 4); return;
    }
    if (tx[0] == 0x50 && n == 4 && tx[1] == 0) {
        s->card_halted = true; s->card_ready = s->card_selected = false;
        s->auth_sector = -1; s->regs[0x08] &= ~8; rfid_timeout(s); return;
    }
    if ((tx[0] == 0x30 || tx[0] == 0xa0) && n == 4 && rfid_authorized(s, tx[1])) {
        unsigned block = tx[1];
        if (tx[0] == 0xa0) {
            if (!block) { rfid_nack(s); return; }
            s->pending_write = block; reply[0] = 0x0a; rfid_reply(s, reply, 1, 4); return;
        }
        memcpy(reply, s->card_memory + block * 16, 16);
        if ((block & 3) == 3) { memset(reply, 0, 6); } /* Key A is never readable */
        uint16_t crc = crc_a(reply, 16); reply[16] = crc; reply[17] = crc >> 8;
        s->card_reads++; rfid_reply(s, reply, 18, 0); return;
    }
    rfid_nack(s);
}

static void rfid_command(M5UnitControl *s, uint8_t command)
{
    uint16_t crc;
    switch (command & 0x0f) {
    case 0: break;
    case 3:
        crc = crc_a(s->rfid_fifo, s->rfid_len);
        s->regs[0x22] = crc; s->regs[0x21] = crc >> 8;
        s->regs[0x05] |= 4;
        break;
    case 0x0c:
        if (s->regs[0x0d] & 0x80) { rfid_transceive(s); }
        break;
    case 0x0e: {
        uint8_t *f = s->rfid_fifo;
        bool good = s->rfid_len == 12 && s->card_present && s->card_selected &&
                    f[1] < 64 && (f[0] == 0x60 || f[0] == 0x61);
        if (good) {
            unsigned trailer = ((f[1] / 4) * 4 + 3) * 16;
            unsigned key = f[0] == 0x60 ? 0 : 10;
            good = !memcmp(f + 2, s->card_memory + trailer + key, 6) && !memcmp(f + 8, s->uid, 4);
        }
        if (good) {
            s->auth_sector = f[1] / 4; s->regs[0x08] |= 8;
            s->rfid_len = 0; s->regs[0x04] = 0x10; s->regs[0x06] = 0;
        } else {
            s->auth_sector = -1; s->regs[0x08] &= ~8;
            s->command_errors++; rfid_timeout(s);
        }
        break;
    }
    case 0x0f: rfid_reset(s); break;
    default:
        s->command_errors++; s->regs[0x06] = 1; s->regs[0x04] = 0x12; break;
    }
}

static uint8_t rfid_read(M5UnitControl *s, uint8_t reg)
{
    if (reg == 9) {
        uint8_t value = s->rfid_len ? s->rfid_fifo[0] : 0;
        if (s->rfid_len) { memmove(s->rfid_fifo, s->rfid_fifo + 1, --s->rfid_len); }
        return value;
    }
    if (reg == 0x0a) { return s->rfid_len; }
    return s->regs[reg];
}

static void rfid_write(M5UnitControl *s, uint8_t reg, uint8_t value)
{
    if (reg == 9) {
        if (s->rfid_len < RFID_FIFO_SIZE) { s->rfid_fifo[s->rfid_len++] = value; }
        else { s->regs[6] |= 0x10; s->command_errors++; }
        return;
    }
    if (reg == 0x0a) { if (value & 0x80) { s->rfid_len = 0; } return; }
    if (reg == 4 || reg == 5) {
        if (value & 0x80) { s->regs[reg] |= value & 0x7f; }
        else { s->regs[reg] &= ~(value & 0x7f); }
        return;
    }
    if (reg == 0x37 || reg == 6 || reg == 0x21 || reg == 0x22) { return; }
    s->regs[reg] = value;
    if (reg == 0x14 && (value & 3) != 3) {
        s->card_ready = s->card_selected = s->card_halted = false;
        s->auth_sector = s->pending_write = -1; s->regs[8] &= ~8;
    }
    if (reg == 1) { rfid_command(s, value); }
    if (reg == 0x0d && (value & 0x80) && (s->regs[1] & 0xf) == 0xc) { rfid_transceive(s); }
    if (reg == 8 && !(value & 8)) { s->auth_sector = -1; }
}

static void scalar_get(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    int64_t value = 0;
    if (!strcmp(name, "x-raw")) { value = s->joystick[0]; }
    else if (!strcmp(name, "y-raw")) { value = s->joystick[1]; }
    else if (!strcmp(name, "button-raw")) { value = s->joystick[2]; }
    else if (!strcmp(name, "counter")) { value = s->counter[0]; }
    else if (!strcmp(name, "keycode")) { value = s->key_count ? s->key_fifo[s->key_head] : 0; }
    else if (!strcmp(name, "queued-keys")) { value = s->key_count; }
    else if (!strcmp(name, "modifier-mode")) { value = s->modifier_mode; }
    else if (!strcmp(name, "key-overflows")) { value = s->key_overflows; }
    else if (!strcmp(name, "i2c-address")) { value = I2C_SLAVE(s)->address; }
    else if (!strcmp(name, "fifo-level")) { value = s->rfid_len; }
    else if (!strcmp(name, "card-reads")) { value = s->card_reads; }
    else if (!strcmp(name, "card-writes")) { value = s->card_writes; }
    else if (!strcmp(name, "command-errors")) { value = s->command_errors; }
    else if (!strcmp(name, "mode")) { value = s->regs[0]; }
    else if (!strcmp(name, "led-rgb") && s->kind == CONTROL_CARDKB) {
        unsigned family = (s->modifier_mode + 1) / 2;
        bool on = !(s->modifier_mode & 1) || (qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) / 250) % 2 == 0;
        value = !on ? 0 : family == 1 ? 0xff0000 : family == 2 ? 0x00ff00 : family == 3 ? 0x0000ff : 0;
    }
    visit_type_int64(v, name, &value, errp);
}

static void scalar_set(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    int64_t value, lo = 0, hi = 255;
    if (!visit_type_int64(v, name, &value, errp)) { return; }
    if (!strcmp(name, "counter")) { lo = -32768; hi = 32767; }
    else if (!strcmp(name, "button-raw")) { hi = 1; }
    if (value < lo || value > hi) { error_setg(errp, "%s outside [%" PRId64 ",%" PRId64 "]", name, lo, hi); return; }
    if (!strcmp(name, "counter")) { s->counter[0] = value; }
    else if (!strcmp(name, "keycode")) {
        if (value && s->key_count == KEY_FIFO_SIZE) { error_setg(errp, "CardKB input FIFO full"); return; }
        if (!value) { s->key_head = s->key_count = 0; }
        else { key_push(s, value); }
    } else { s->joystick[!strcmp(name, "x-raw") ? 0 : !strcmp(name, "y-raw") ? 1 : 2] = value; }
    input_changed(s);
}

static void bool_get(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    bool value = !strcmp(name, "pressed") ? s->pressed[0] :
                 !strcmp(name, "switch-on") ? s->switch_on :
                 !strcmp(name, "card-present") ? s->card_present :
                 !strcmp(name, "selected") ? s->card_selected : (s->regs[8] & 8) != 0;
    visit_type_bool(v, name, &value, errp);
}

static void bool_set(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    bool value;
    if (!visit_type_bool(v, name, &value, errp)) { return; }
    if (!strcmp(name, "pressed")) { s->pressed[0] = value; }
    else if (!strcmp(name, "switch-on")) { s->switch_on = value; }
    else {
        if (s->card_present != value) {
            s->card_ready = s->card_selected = s->card_halted = false;
            s->auth_sector = s->pending_write = -1; s->regs[8] &= ~8;
        }
        s->card_present = value;
    }
    input_changed(s);
}

static void array_get(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    QList *list = qlist_new();
    unsigned count = !strcmp(name, "keys") || !strcmp(name, "key-ids") ? CARD_KEYS : !strcmp(name, "led-rgb") ? (s->kind == CONTROL_ENCODER ? 2 : 9) : 8;
    for (unsigned i = 0; i < count; i++) {
        if (!strcmp(name, "key-ids")) { qlist_append_str(list, key_ids[i]); }
        else if (!strcmp(name, "keys")) { qlist_append_bool(list, s->keys[i]); }
        else if (!strcmp(name, "pressed")) { qlist_append_bool(list, s->pressed[i]); }
        else if (!strcmp(name, "counters")) { qlist_append_int(list, s->counter[i]); }
        else if (!strcmp(name, "increments")) { qlist_append_int(list, s->increments[i]); }
        else { qlist_append_int(list, s->leds[i]); }
    }
    QObject *value = QOBJECT(list);
    visit_type_any(v, name, &value, errp);
    qobject_unref(value);
}

static void array_set(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    QObject *value = NULL;
    int64_t numbers[CARD_KEYS] = {0};
    bool booleans[CARD_KEYS] = {false};
    unsigned count = !strcmp(name, "keys") ? CARD_KEYS : 8, i = 0;
    bool bool_array = strcmp(name, "counters") != 0;
    if (!visit_type_any(v, name, &value, errp)) { return; }
    QList *list = qobject_to(QList, value);
    if (!list || qlist_size(list) != count) {
        error_setg(errp, "%s requires exactly %u items", name, count); goto out;
    }
    const QListEntry *entry;
    QLIST_FOREACH_ENTRY(list, entry) {
        QObject *item = qlist_entry_obj(entry);
        if (bool_array) {
            QBool *b = qobject_to(QBool, item);
            if (!b) { error_setg(errp, "%s items must be bool", name); goto out; }
            booleans[i] = qbool_get_bool(b);
        } else {
            QNum *n = qobject_to(QNum, item);
            if (!n || !qnum_get_try_int(n, &numbers[i]) || numbers[i] < INT32_MIN || numbers[i] > INT32_MAX) {
                error_setg(errp, "counter items must be int32"); goto out;
            }
        }
        i++;
    }
    if (!strcmp(name, "keys")) {
        unsigned needed = 0;
        for (i = 0; i < count; i++) { if (booleans[i] && !s->keys[i] && i != 23 && i != 24 && i != 35) { needed++; } }
        if (needed > KEY_FIFO_SIZE - s->key_count) { error_setg(errp, "CardKB input FIFO full"); goto out; }
        /* Modifiers precede simultaneous characters; all validation is atomic. */
        for (unsigned j = 0; j < 3; j++) {
            i = (unsigned[]){23, 24, 35}[j];
            if (booleans[i] && !s->keys[i]) { key_press(s, i); }
        }
        for (i = 0; i < count; i++) {
            if (i != 23 && i != 24 && i != 35 && booleans[i] && !s->keys[i]) { key_press(s, i); }
        }
        memcpy(s->keys, booleans, sizeof(s->keys));
    } else if (!strcmp(name, "pressed")) { memcpy(s->pressed, booleans, sizeof(s->pressed)); }
    else {
        for (i = 0; i < count; i++) {
            uint32_t delta = (uint32_t)numbers[i] - (uint32_t)s->counter[i];
            s->increments[i] = (uint32_t)s->increments[i] + delta;
            s->counter[i] = numbers[i];
        }
    }
    input_changed(s);
out:
    qobject_unref(value);
}

static void string_get(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    const uint8_t *data = !strcmp(name, "uid-hex") ? s->uid : s->card_memory;
    unsigned count = !strcmp(name, "uid-hex") ? s->uid_len : sizeof(s->card_memory);
    char *text = g_malloc(count * 2 + 1);
    for (unsigned i = 0; i < count; i++) { g_snprintf(text + i * 2, 3, "%02x", data[i]); }
    visit_type_str(v, name, &text, errp);
    g_free(text);
}

static void string_set(Object *obj, Visitor *v, const char *name, void *opaque, Error **errp)
{
    M5UnitControl *s = opaque;
    char *text = NULL;
    uint8_t bytes[1024];
    if (!visit_type_str(v, name, &text, errp)) { return; }
    size_t length = strlen(text), count = length / 2;
    bool uid = !strcmp(name, "uid-hex");
    if ((length & 1) || (uid ? count != 4 && count != 7 && count != 10 : count != 1024)) {
        error_setg(errp, uid ? "UID must be 4, 7 or 10 complete bytes" : "card-data-hex must contain exactly 1024 bytes"); goto out;
    }
    for (unsigned i = 0; i < count; i++) {
        int hi = g_ascii_xdigit_value(text[i * 2]), lo = g_ascii_xdigit_value(text[i * 2 + 1]);
        if (hi < 0 || lo < 0) { error_setg(errp, "%s must contain hexadecimal bytes only", name); goto out; }
        bytes[i] = hi * 16 + lo;
    }
    if (uid) {
        memcpy(s->uid, bytes, count); s->uid_len = count;
        s->card_ready = s->card_selected = s->card_halted = false;
        s->auth_sector = s->pending_write = -1; s->regs[8] &= ~8;
    } else {
        memcpy(s->card_memory, bytes, sizeof(s->card_memory));
        s->auth_sector = s->pending_write = -1; s->regs[8] &= ~8;
    }
    input_changed(s);
out:
    g_free(text);
}

static void snapshot_registers(M5UnitControl *s)
{
    memcpy(s->read_snapshot, s->regs, 256);
    if (s->kind == CONTROL_JOYSTICK) { memcpy(s->read_snapshot + 0x52, s->joystick, 3); }
    else if (s->kind == CONTROL_ENCODER) {
        uint16_t count = s->counter[0];
        s->read_snapshot[0x10] = count; s->read_snapshot[0x11] = count >> 8;
        /* Executable UIFlow driver uses active-low. The 2022 PDF says the
         * opposite: this is the explicitly chosen driver-compatibility lane. */
        s->read_snapshot[0x20] = !s->pressed[0]; s->read_snapshot[0x21] = 0;
    } else if (s->kind == CONTROL_ENCODER8) {
        for (unsigned i = 0; i < 8; i++) {
            uint32_t count = s->counter[i], increment = s->increments[i];
            for (unsigned b = 0; b < 4; b++) {
                s->read_snapshot[i * 4 + b] = count >> (b * 8);
                s->read_snapshot[0x20 + i * 4 + b] = increment >> (b * 8);
            }
            s->read_snapshot[0x50 + i] = !s->pressed[i];
        }
        s->read_snapshot[0x60] = s->switch_on;
        for (unsigned i = 0; i < 9; i++) {
            s->read_snapshot[0x70 + i * 3] = s->leds[i] >> 16;
            s->read_snapshot[0x71 + i * 3] = s->leds[i] >> 8;
            s->read_snapshot[0x72 + i * 3] = s->leds[i];
        }
        s->read_snapshot[0xfe] = 1; /* Emulated MCU protocol revision */
        s->read_snapshot[0xff] = I2C_SLAVE(s)->address;
    }
}

static int control_event(I2CSlave *dev, enum i2c_event event)
{
    M5UnitControl *s = M5_UNIT_CONTROL(dev);
    if (event == I2C_START_SEND || event == I2C_START_SEND_ASYNC) {
        s->unit->transactions++; s->write_pos = 0; s->reading = false;
    } else if (event == I2C_START_RECV) {
        s->unit->transactions++; s->read_pos = 0; s->reading = true;
        snapshot_registers(s);
    } else if (event == I2C_FINISH && s->reading) {
        s->memory_request = false; s->reading = false;
    }
    return 0;
}

static int control_send(I2CSlave *dev, uint8_t value)
{
    M5UnitControl *s = M5_UNIT_CONTROL(dev);
    s->unit->written_bytes++;
    if (s->write_pos++ == 0) {
        s->pointer = s->write_base = value; s->memory_request = true;
        memset(s->led_write, 0, sizeof(s->led_write)); return 0;
    }
    uint8_t reg = s->pointer;
    if (s->kind == CONTROL_RFID2) {
        rfid_write(s, reg, value);
        if (reg != 9) { s->pointer++; }
    } else if (s->kind == CONTROL_ENCODER) {
        if (s->write_base == 0x30 && s->write_pos >= 2 && s->write_pos <= 5) {
            s->led_write[s->write_pos - 2] = value;
            if (s->write_pos == 5) {
                uint8_t index = s->led_write[0];
                if (index > 2) { return 1; }
                uint32_t color = (s->led_write[1] << 16) | (s->led_write[2] << 8) | s->led_write[3];
                bool changed = false;
                for (unsigned i = 0; i < 2; i++) {
                    if (!index || index == i + 1) {
                        changed |= s->leds[i] != color; s->leds[i] = color;
                    }
                }
                if (changed) { output_changed(s); }
            }
        } else if (reg == 0 && value <= 1) { s->regs[0] = value; }
        else { return 1; }
        s->pointer++;
    } else if (s->kind == CONTROL_ENCODER8) {
        if (reg <= 0x1f) {
            unsigned i = reg / 4, shift = (reg % 4) * 8;
            s->counter[i] = ((uint32_t)s->counter[i] & ~(0xffU << shift)) | ((uint32_t)value << shift);
        } else if (reg >= 0x40 && reg <= 0x47) {
            if (value == 1) { s->counter[reg - 0x40] = 0; s->increments[reg - 0x40] = 0; }
        } else if (reg >= 0x70 && reg <= 0x8a) {
            unsigned i = (reg - 0x70) / 3, shift = (2 - (reg - 0x70) % 3) * 8;
            uint32_t color = (s->leds[i] & ~(0xffU << shift)) | ((uint32_t)value << shift);
            if (s->leds[i] != color) { s->leds[i] = color; output_changed(s); }
        } else if (reg == 0xff && value >= 8 && value <= 0x77) {
            BusChild *child;
            QTAILQ_FOREACH(child, &BUS(s->unit->bus)->children, sibling) {
                I2CSlave *other = I2C_SLAVE(child->child);
                if (other != dev && other->address == value) { return 1; }
            }
            i2c_slave_set_address(dev, value);
        } else { return 1; }
        s->pointer++;
    } else if (s->kind == CONTROL_JOYSTICK) { return 1; }
    /* CardKB v1.1 accepts legacy writes but has no invented v2 report bank. */
    return 0;
}

static uint8_t control_recv(I2CSlave *dev)
{
    M5UnitControl *s = M5_UNIT_CONTROL(dev);
    s->unit->read_bytes++;
    if (s->kind == CONTROL_RFID2) {
        uint8_t reg = s->pointer;
        if (reg != 9) { s->pointer++; }
        return rfid_read(s, reg);
    }
    if (s->kind == CONTROL_CARDKB) {
        /* A shared new driver may probe register 0x02. It must see legacy,
         * not accidentally interpret the next keycode as V2 report length. */
        if (s->memory_request) { return s->pointer == 2 ? 0 : 0xff; }
        uint8_t result = s->key_count ? s->key_fifo[s->key_head] : 0;
        if (s->key_count) { s->key_head = (s->key_head + 1) % KEY_FIFO_SIZE; s->key_count--; }
        return result;
    }
    uint8_t reg = s->pointer++, value = s->read_snapshot[reg];
    s->read_pos++;
    if (s->kind == CONTROL_ENCODER8 && reg >= 0x20 && reg <= 0x3f && (reg & 3) == 3 && s->read_pos >= 4) {
        /* Explicit model policy: increment is consumed only after its complete
         * LE int32 has been read. Partial reads cannot erase remaining bytes. */
        s->increments[(reg - 0x20) / 4] = 0;
    }
    return value;
}

static void add_int(M5UnitControl *s, const char *name, bool writable)
{
    object_property_add(OBJECT(s->unit), name, "int", scalar_get,
                        writable ? scalar_set : NULL, NULL, s);
}

static void add_bool(M5UnitControl *s, const char *name, bool writable)
{
    object_property_add(OBJECT(s->unit), name, "bool", bool_get,
                        writable ? bool_set : NULL, NULL, s);
}

static void add_array(M5UnitControl *s, const char *name, bool writable)
{
    object_property_add(OBJECT(s->unit), name, "any", array_get,
                        writable ? array_set : NULL, NULL, s);
}

static void add_string(M5UnitControl *s, const char *name)
{
    object_property_add(OBJECT(s->unit), name, "str", string_get, string_set, NULL, s);
}

bool m5_unit_controls_supported(const char *unit_id)
{
    static const char *const ids[] = {"joystick-v11", "encoder", "8encoder", "cardkb", "rfid2"};
    for (unsigned i = 0; i < G_N_ELEMENTS(ids); i++) { if (!strcmp(unit_id, ids[i])) { return true; } }
    return false;
}

void m5_unit_controls_realize(M5Unit *unit, Error **errp)
{
    M5UnitControl *s;
    unsigned address;
    if (!unit->bus) { error_setg(errp, "control Unit requires a routed I2C bus"); return; }
    if (!m5_unit_controls_supported(unit->unit_id)) { error_setg(errp, "unsupported control Unit"); return; }
    s = M5_UNIT_CONTROL(qdev_new(TYPE_M5_UNIT_CONTROL));
    s->unit = unit;
    s->auth_sector = s->pending_write = -1;
    if (!strcmp(unit->unit_id, "joystick-v11")) {
        s->kind = CONTROL_JOYSTICK; address = 0x52;
        s->joystick[0] = s->joystick[1] = 128;
        add_int(s, "x-raw", true); add_int(s, "y-raw", true); add_int(s, "button-raw", true);
    } else if (!strcmp(unit->unit_id, "encoder")) {
        s->kind = CONTROL_ENCODER; address = 0x40;
        add_int(s, "counter", true); add_bool(s, "pressed", true);
        add_int(s, "mode", false); add_array(s, "led-rgb", false);
    } else if (!strcmp(unit->unit_id, "8encoder")) {
        s->kind = CONTROL_ENCODER8; address = 0x41;
        add_array(s, "counters", true); add_array(s, "increments", false);
        add_array(s, "pressed", true); add_bool(s, "switch-on", true); add_array(s, "led-rgb", false);
    } else if (!strcmp(unit->unit_id, "cardkb")) {
        s->kind = CONTROL_CARDKB; address = 0x5f;
        add_int(s, "keycode", true); add_array(s, "keys", true);
        add_array(s, "key-ids", false);
        add_int(s, "queued-keys", false); add_int(s, "modifier-mode", false);
        add_int(s, "key-overflows", false); add_int(s, "led-rgb", false);
    } else {
        s->kind = CONTROL_RFID2; address = 0x28; s->uid_len = 4;
        static const uint8_t uid[] = {4, 1, 2, 3}; memcpy(s->uid, uid, 4);
        /* Deterministic blank synthetic card, transport keys only. No real
         * user card contents, production keys or secure-key claims. */
        for (unsigned i = 0; i < 16; i++) {
            uint8_t *trailer = s->card_memory + (i * 4 + 3) * 16;
            memset(trailer, 0xff, 6); trailer[6] = 0xff; trailer[7] = 7;
            trailer[8] = 0x80; trailer[9] = 0x69; memset(trailer + 10, 0xff, 6);
        }
        memcpy(s->card_memory, uid, 4); s->card_memory[4] = 4 ^ 1 ^ 2 ^ 3;
        rfid_reset(s);
        add_bool(s, "card-present", true); add_string(s, "uid-hex"); add_string(s, "card-data-hex");
        add_bool(s, "selected", false); add_bool(s, "authenticated", false);
        add_int(s, "fifo-level", false); add_int(s, "card-reads", false);
        add_int(s, "card-writes", false); add_int(s, "command-errors", false);
    }
    add_int(s, "i2c-address", false);
    object_property_add_child(OBJECT(unit), "controller", OBJECT(s));
    qdev_prop_set_uint8(DEVICE(s), "address", address);
    i2c_slave_realize_and_unref(I2C_SLAVE(s), unit->bus, errp);
}

static void control_class_init(ObjectClass *klass, void *data)
{
    I2CSlaveClass *i2c = I2C_SLAVE_CLASS(klass);
    i2c->event = control_event; i2c->send = control_send; i2c->recv = control_recv;
}

static const TypeInfo control_info = {
    .name = TYPE_M5_UNIT_CONTROL, .parent = TYPE_I2C_SLAVE,
    .instance_size = sizeof(M5UnitControl), .class_init = control_class_init,
};

static void control_register_types(void) { type_register_static(&control_info); }
type_init(control_register_types)
