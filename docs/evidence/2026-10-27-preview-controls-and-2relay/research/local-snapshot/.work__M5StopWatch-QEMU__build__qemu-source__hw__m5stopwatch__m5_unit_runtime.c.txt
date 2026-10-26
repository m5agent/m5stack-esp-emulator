/*
 * Session-scoped Grove Units on real GPIO and I2C controller data planes.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Wiring is supplied by the verified host connector catalog.  Physical values
 * enter sensor models; the guest still performs transactions and compensation.
 */
#include "qemu/osdep.h"
#include "qemu/error-report.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qom/qom-qobject.h"
#include "qapi/qmp/qdict.h"
#include "qapi/qmp/qlist.h"
#include "qapi/qmp/qjson.h"
#include "qapi/qmp/qnum.h"
#include "hw/i2c/i2c.h"
#include "hw/qdev-properties.h"
#include "m5stopwatch.h"
#include <math.h>

#include "m5_unit_runtime.h"
typedef enum { SENSOR_SHT30, SENSOR_QMP6988 } SensorKind;
typedef struct M5UnitI2C {
    I2CSlave parent_obj;
    M5Unit *unit;
    SensorKind sensor;
    uint8_t regs[256], response[8];
    uint16_t command;
    unsigned write_pos, read_pos;
    uint8_t pointer;
    int64_t conversion_due;
    uint64_t transactions, read_bytes, written_bytes;
} M5UnitI2C;
OBJECT_DECLARE_SIMPLE_TYPE(M5UnitI2C, M5_UNIT_I2C)

typedef struct UnitPort { int sda, scl; I2CBus *bus; } UnitPort;
static UnitPort ports[MAX_UNIT_PORTS];
static unsigned port_count;

extern bool esp32_gpio_matrix_i2c_pins(unsigned controller, bool s3,
                                     int *sda, int *scl);

I2CBus *m5_unit_i2c_route(I2CBus *fallback, unsigned controller, bool s3)
{
    int sda, scl;
    if (!port_count || !esp32_gpio_matrix_i2c_pins(controller, s3, &sda, &scl)) {
        return fallback;
    }
    for (unsigned i = 0; i < port_count; i++) {
        if (ports[i].sda == sda && ports[i].scl == scl) {
            return ports[i].bus;
        }
    }
    return fallback;
}

static void get_u64(Object *obj, Visitor *v, const char *name,
                    void *opaque, Error **errp)
{
    uint64_t value = *(uint64_t *)opaque;
    visit_type_uint64(v, name, &value, errp);
}

static void get_number(Object *obj, Visitor *v, const char *name,
                       void *opaque, Error **errp)
{
    double value = *(double *)opaque;
    visit_type_number(v, name, &value, errp);
}

static void set_number(Object *obj, Visitor *v, const char *name,
                       void *opaque, Error **errp)
{
    double value, lo, hi;
    if (!visit_type_number(v, name, &value, errp)) {
        return;
    }
    if (!strcmp(name, "temperature-c")) { lo = -40; hi = 120; }
    else if (!strcmp(name, "humidity-pct")) { lo = 0; hi = 100; }
    else { lo = 30000; hi = 110000; }
    if (!isfinite(value) || value < lo || value > hi) {
        error_setg(errp, "%s must be finite and in [%g,%g]", name, lo, hi);
        return;
    }
    *(double *)opaque = value;
    M5_UNIT(obj)->input_events++;
}

static void get_pressed(Object *obj, Visitor *v, const char *name,
                        void *opaque, Error **errp)
{
    bool value = M5_UNIT(obj)->pressed;
    visit_type_bool(v, name, &value, errp);
}

static void set_pressed(Object *obj, Visitor *v, const char *name,
                        void *opaque, Error **errp)
{
    M5Unit *unit = M5_UNIT(obj);
    bool value;
    if (visit_type_bool(v, name, &value, errp)) {
        if (unit->pressed != value) { unit->input_events++; }
        unit->pressed = value;
        esp32_gpio_set_input(unit->white, !value);
    }
}

static void get_input(Object *obj, Visitor *v, const char *name,
                      void *opaque, Error **errp)
{
    bool value = esp32_gpio_get_line(M5_UNIT(obj)->white);
    visit_type_bool(v, name, &value, errp);
}

static void get_output(Object *obj, Visitor *v, const char *name,
                       void *opaque, Error **errp)
{
    bool value = esp32_gpio_get_line(M5_UNIT(obj)->yellow);
    visit_type_bool(v, name, &value, errp);
}

static void output_changed(void *opaque, int pin, int level)
{
    M5Unit *unit = opaque;
    if (unit->previous_output != level) {
        unit->previous_output = level;
        unit->output_transitions++;
    }
}

static uint8_t sht_crc(const uint8_t *bytes, size_t count)
{
    uint8_t crc = 0xff;
    for (size_t i = 0; i < count; i++) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; bit++) {
            crc = (crc & 0x80) ? (crc << 1) ^ 0x31 : crc << 1;
        }
    }
    return crc;
}

static bool sht_measure_command(uint16_t cmd)
{
    switch (cmd) {
    case 0x2c06: case 0x2c0d: case 0x2c10:
    case 0x2400: case 0x240b: case 0x2416:
        return true;
    default: return false;
    }
}

static void sht_response(M5UnitI2C *s)
{
    memset(s->response, 0xff, sizeof(s->response));
    if (sht_measure_command(s->command)) {
        uint16_t t = llround((s->unit->temperature_c + 45) * 65535 / 175);
        uint16_t rh = llround(s->unit->humidity_pct * 65535 / 100);
        s->response[0] = t >> 8; s->response[1] = t;
        s->response[2] = sht_crc(s->response, 2);
        s->response[3] = rh >> 8; s->response[4] = rh;
        s->response[5] = sht_crc(s->response + 3, 2);
    } else if (s->command == 0xf32d) {
        s->response[0] = s->regs[0]; s->response[1] = s->regs[1];
        s->response[2] = sht_crc(s->response, 2);
    }
}

/* Synthetic OTP coefficients, independently checked against the unmodified
 * official QMP6988 driver. They do not represent physical factory calibration.
 */
static double qmp_temperature(int32_t dt)
{
    return 640 - 6.30e-3 * dt - 1.90e-11 * (double)dt * dt;
}

static double qmp_pressure(int32_t dp, double tr)
{
    double p = dp;
    return 20000 + .1 * tr + .033 * p + 2.10e-7 * tr * p
        + 1.20e-8 * tr * tr - 6.30e-10 * p * p
        + 2.90e-13 * p * tr * tr + 2.10e-15 * p * p * tr
        + 1.30e-16 * p * p * p;
}

static int32_t qmp_inverse(double target, bool temperature, double tr)
{
    int32_t lo = -(1 << 23), hi = (1 << 23) - 1;
    while (lo < hi) {
        int32_t mid = lo + (hi - lo) / 2;
        double value = temperature ? qmp_temperature(mid) : qmp_pressure(mid, tr);
        if ((value < target) == !temperature) { lo = mid + 1; }
        else { hi = mid; }
    }
    if (lo > -(1 << 23)) {
        double a = temperature ? qmp_temperature(lo) : qmp_pressure(lo, tr);
        double b = temperature ? qmp_temperature(lo - 1) : qmp_pressure(lo - 1, tr);
        if (fabs(b - target) < fabs(a - target)) { lo--; }
    }
    return lo;
}

static void qmp_update(M5UnitI2C *s)
{
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (!(s->regs[0xf4] & 3) || now < s->conversion_due) { return; }
    int32_t dt = qmp_inverse(s->unit->temperature_c * 256, true, 0);
    int32_t dp = qmp_inverse(s->unit->pressure_pa, false, qmp_temperature(dt));
    uint32_t raw[] = { dp + (1 << 23), dt + (1 << 23) };
    for (unsigned i = 0; i < 2; i++) {
        s->regs[0xf7 + i * 3] = raw[i] >> 16;
        s->regs[0xf8 + i * 3] = raw[i] >> 8;
        s->regs[0xf9 + i * 3] = raw[i];
    }
    if ((s->regs[0xf4] & 3) == 1) { s->regs[0xf4] &= ~3; }
    s->regs[0xf3] = 0;
    s->conversion_due = now + 8 * 1000000;
}

static int sensor_event(I2CSlave *dev, enum i2c_event event)
{
    M5UnitI2C *s = M5_UNIT_I2C(dev);
    if (event == I2C_START_SEND || event == I2C_START_RECV) {
        s->transactions++; s->unit->transactions++;
        s->write_pos = s->read_pos = 0;
        if (event == I2C_START_RECV && s->sensor == SENSOR_SHT30) {
            sht_response(s);
        }
    }
    return 0;
}

static int sensor_write(I2CSlave *dev, uint8_t value)
{
    M5UnitI2C *s = M5_UNIT_I2C(dev);
    s->written_bytes++; s->unit->written_bytes++;
    if (s->sensor == SENSOR_SHT30) {
        if (!s->write_pos) { s->command = value << 8; }
        else if (s->write_pos == 1) {
            s->command |= value;
            if (s->command == 0x30a2 || s->command == 0x3041) {
                s->regs[0] = s->regs[1] = 0;
            } else if (s->command == 0x306d) { s->regs[0] |= 0x20; }
            else if (s->command == 0x3066) { s->regs[0] &= ~0x20; }
        } else { return 1; }
    } else if (!s->write_pos) { s->pointer = value; }
    else {
        if (s->pointer == 0xe0 && value == 0xe6) {
            s->regs[0xf1] = s->regs[0xf4] = s->regs[0xf5] = 0;
        } else if (s->pointer == 0xf1 || s->pointer == 0xf4 || s->pointer == 0xf5) {
            s->regs[s->pointer] = value;
            if (s->pointer == 0xf4 && (value & 3)) {
                s->regs[0xf3] = 8;
                s->conversion_due = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 8000000;
            }
        }
        s->pointer++;
    }
    s->write_pos++;
    return 0;
}

static uint8_t sensor_read(I2CSlave *dev)
{
    M5UnitI2C *s = M5_UNIT_I2C(dev);
    s->read_bytes++; s->unit->read_bytes++;
    if (s->sensor == SENSOR_SHT30) {
        return s->read_pos < sizeof(s->response) ? s->response[s->read_pos++] : 0xff;
    }
    qmp_update(s);
    if (s->pointer == 0xf3) {
        s->pointer++;
        return s->regs[0xf3];
    }
    return s->regs[s->pointer++];
}

static void counters(Object *obj, uint64_t *transactions,
                     uint64_t *read_bytes, uint64_t *written_bytes)
{
    object_property_add(obj, "transactions", "uint64", get_u64, NULL, NULL, transactions);
    object_property_add(obj, "read-bytes", "uint64", get_u64, NULL, NULL, read_bytes);
    object_property_add(obj, "written-bytes", "uint64", get_u64, NULL, NULL, written_bytes);
}

static void sensor_attach(M5Unit *unit, const char *name,
                          uint8_t address, SensorKind sensor)
{
    M5UnitI2C *s = M5_UNIT_I2C(qdev_new(TYPE_M5_UNIT_I2C));
    s->unit = unit; s->sensor = sensor;
    if (sensor == SENSOR_QMP6988) {
        static const uint8_t otp[25] = {0x4e, 0x20, [18] = 0x02, [19] = 0x80};
        memcpy(s->regs + 0xa0, otp, sizeof(otp));
        s->regs[0xd1] = 0x5c;
    }
    object_property_add_child(OBJECT(unit), name, OBJECT(s));
    qdev_prop_set_uint8(DEVICE(s), "address", address);
    counters(OBJECT(s), &s->transactions, &s->read_bytes, &s->written_bytes);
    i2c_slave_realize_and_unref(I2C_SLAVE(s), unit->bus, &error_fatal);
}

static void unit_realize(DeviceState *dev, Error **errp)
{
    M5Unit *u = M5_UNIT(dev);
    counters(OBJECT(u), &u->transactions, &u->read_bytes, &u->written_bytes);
    object_property_add(OBJECT(u), "input-events", "uint64", get_u64, NULL, NULL, &u->input_events);
    object_property_add(OBJECT(u), "output-transitions", "uint64", get_u64, NULL, NULL, &u->output_transitions);
    if (u->kind == UNIT_BUTTON) {
        object_property_add(OBJECT(u), "pressed", "bool", get_pressed, set_pressed, NULL, NULL);
        object_property_add(OBJECT(u), "input-level", "bool", get_input, NULL, NULL, NULL);
        esp32_gpio_set_input(u->white, !u->pressed);
    } else if (u->kind == UNIT_RELAY) {
        object_property_add(OBJECT(u), "output-level", "bool", get_output, NULL, NULL, NULL);
        u->previous_output = esp32_gpio_get_line(u->yellow);
        esp32_gpio_add_out_listener(u->yellow, output_changed, u);
    } else if (u->kind == UNIT_GPIO) {
        m5_unit_gpio_realize(u, u->s3, errp);
    } else {
        for (unsigned i = 0; i < port_count; i++) {
            if (ports[i].sda == u->yellow && ports[i].scl == u->white) { u->bus = ports[i].bus; }
        }
        if (!u->bus) {
            if (port_count >= MAX_UNIT_PORTS) { error_setg(errp, "too many Unit I2C ports"); return; }
            u->bus = i2c_init_bus(dev, "i2c");
            ports[port_count++] = (UnitPort){u->yellow, u->white, u->bus};
            m5stopwatch_soft_i2c_init_pins(u->bus, u->yellow, u->white);
        }
        if (u->kind == UNIT_ENV_III) {
        object_property_add(OBJECT(u), "temperature-c", "number", get_number, set_number, NULL, &u->temperature_c);
        object_property_add(OBJECT(u), "humidity-pct", "number", get_number, set_number, NULL, &u->humidity_pct);
        object_property_add(OBJECT(u), "pressure-pa", "number", get_number, set_number, NULL, &u->pressure_pa);
            sensor_attach(u, "sht30", 0x44, SENSOR_SHT30);
            sensor_attach(u, "qmp6988", 0x70, SENSOR_QMP6988);
        } else { m5_unit_extra_realize(u, errp); }
    }
}

static void unit_class_init(ObjectClass *klass, void *data)
{
    DEVICE_CLASS(klass)->realize = unit_realize;
}

static void sensor_class_init(ObjectClass *klass, void *data)
{
    I2CSlaveClass *sc = I2C_SLAVE_CLASS(klass);
    sc->event = sensor_event; sc->send = sensor_write; sc->recv = sensor_read;
}

void m5_unit_runtime_init(bool s3)
{
    const char *path = getenv("M5_UNIT_CONFIG");
    char *text = NULL;
    gsize size;
    GError *gerror = NULL;
    if (!path || !*path) { return; }
    if (!g_file_get_contents(path, &text, &size, &gerror) || size > 65536) {
        error_report("Unit config cannot be read or exceeds 64 KiB"); exit(1);
    }
    QObject *value = qobject_from_json(text, &error_fatal);
    g_free(text);
    QDict *root = qobject_to(QDict, value);
    if (!root || qdict_get_try_int(root, "schema_version", 0) != 1) {
        error_report("Unit config schema_version must be 1"); exit(1);
    }
    QList *attachments = qdict_get_qlist(root, "attachments");
    if (!attachments || qlist_size(attachments) > 16) {
        error_report("Unit config needs at most 16 attachments"); exit(1);
    }
    Object *manager = object_new("container");
    static uint64_t schema = 1;
    object_property_add_child(qdev_get_machine(), "units", manager);
    object_property_add(manager, "schema-version", "uint64", get_u64, NULL, NULL, &schema);
    const QListEntry *entry;
    QLIST_FOREACH_ENTRY(attachments, entry) {
        QDict *row = qobject_to(QDict, qlist_entry_obj(entry));
        QDict *pins = row ? qdict_get_qdict(row, "pins") : NULL;
        const char *id = row ? qdict_get_try_str(row, "id") : NULL;
        const char *unit_id = row ? qdict_get_try_str(row, "unit_id") : NULL;
        if (!row || !pins || !id || !*id || strlen(id) > 64 ||
            strspn(id, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != strlen(id) || !unit_id) {
            error_report("invalid Unit attachment identity/pins"); exit(1);
        }
        M5Unit *u = M5_UNIT(qdev_new(TYPE_M5_UNIT));
        u->yellow = qdict_get_int(pins, "yellow"); u->white = qdict_get_int(pins, "white");
        if (u->yellow < 0 || u->white < 0 || u->yellow >= (s3 ? 49 : 40) ||
            u->white >= (s3 ? 49 : 40) || u->yellow == u->white) {
            error_report("Unit pins are outside the selected SoC"); exit(1);
        }
        if (!strcmp(unit_id, "button")) { u->kind = UNIT_BUTTON; }
        else if (!strcmp(unit_id, "relay")) { u->kind = UNIT_RELAY; }
        else if (!strcmp(unit_id, "env-iii")) { u->kind = UNIT_ENV_III; }
        else if (m5_unit_gpio_supported(unit_id)) { u->kind = UNIT_GPIO; }
        else if (m5_unit_extra_supported(unit_id)) { u->kind = UNIT_EXTRA; }
        else { error_report("Unit model is unavailable: %s", unit_id); exit(1); }
        u->unit_id = g_strdup(unit_id); u->s3 = s3;
        u->temperature_c = 25; u->humidity_pct = 50; u->pressure_pa = 101325;
        object_property_add_child(manager, id, OBJECT(u));
        qdev_realize_and_unref(DEVICE(u), NULL, &error_fatal);
        QDict *initial = qdict_get_qdict(row, "initial");
        if (initial) {
            const QDictEntry *field;
            for (field = qdict_first(initial); field; field = qdict_next(initial, field)) {
                object_property_set_qobject(OBJECT(u), qdict_entry_key(field),
                                            qdict_entry_value(field), &error_fatal);
            }
        }
    }
    object_unref(manager); qobject_unref(value);
}

static const TypeInfo types[] = {
    { .name = TYPE_M5_UNIT, .parent = TYPE_DEVICE,
      .instance_size = sizeof(M5Unit), .class_init = unit_class_init },
    { .name = TYPE_M5_UNIT_I2C, .parent = TYPE_I2C_SLAVE,
      .instance_size = sizeof(M5UnitI2C), .class_init = sensor_class_init },
};
DEFINE_TYPES(types)

/* Optional modules fail closed until their implementation is linked. */
bool m5_unit_extra_supported(const char *id)
{
    return m5_unit_sensor_supported(id) ||
           m5_unit_controls_supported(id);
}
void m5_unit_extra_realize(M5Unit *u, Error **errp)
{
    if (m5_unit_sensor_supported(u->unit_id)) {
        m5_unit_sensor_realize(u, errp);
    } else if (m5_unit_controls_supported(u->unit_id)) {
        m5_unit_controls_realize(u, errp);
    } else { error_setg(errp, "Unit protocol module is unavailable"); }
}
