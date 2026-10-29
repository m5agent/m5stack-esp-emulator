/* Endpoint transport shim: a test register bank with independent lifetime.
 * It checks bridge routing/ACK/reset ownership, not QEMU peripheral identity
 * or a physical device. The real bridge and GPIO algorithms follow below. */
typedef struct I2CBus {
    uint8_t regs[256], pointer;
    unsigned starts, ends, sends, receives, nacks;
    bool selected, read, pointer_pending;
} I2CBus;
static int i2c_start_transfer(I2CBus *s, int addr, int read)
{
    s->starts++;
    s->selected = addr == 0x58;
    s->read = read;
    s->pointer_pending = !read;
    return s->selected ? 0 : -1;
}
static void i2c_end_transfer(I2CBus *s)
{ s->ends++; s->selected = false; }
static int i2c_send(I2CBus *s, int byte)
{
    s->sends++;
    if (!s->selected || s->read) { return -1; }
    if (s->pointer_pending) { s->pointer = byte; s->pointer_pending = false; }
    else { s->regs[s->pointer++] = byte; }
    return 0;
}
static int i2c_recv(I2CBus *s)
{
    s->receives++;
    assert(s->selected && s->read);
    return s->regs[s->pointer++];
}
static void i2c_nack(I2CBus *s) { s->nacks++; }

/* BRIDGE_SOURCE */

static void master_latch(unsigned pin, bool high)
{ gpio_write((pin < 32 ? 0x08 : 0x14) + (high ? 0 : 4), 1u << (pin & 31)); }
static unsigned master_read(unsigned pin)
{
    return !!(esp32_gpio_read(&controller, pin < 32 ? 0x3c : 0x40, 4) &
              (1u << (pin & 31)));
}
static void master_configure_pin(unsigned pin)
{
    uint32_t mux = (g_iomux_regs[pin] & ~((7u << 12) | (1u << 7) | (1u << 8))) |
                   (1u << 12) | (1u << 9);
    esp32_gpio_iomux_write(&controller, 4 + pin * 4, mux, 4);
    gpio_write(0x74 + pin * 4, 1u << 2);
    master_latch(pin, true);
    gpio_write(pin < 32 ? 0x24 : 0x30, 1u << (pin & 31));
    gpio_write(0x554 + pin * 4, 256);
}
static void master_configure(M5StopwatchSoftI2C *s)
{
    master_configure_pin(s->scl_pin);
    master_configure_pin(s->sda_pin);
    assert(master_read(s->sda_pin) == 1 && master_read(s->scl_pin) == 1);
}
static void master_start(M5StopwatchSoftI2C *s)
{
    master_latch(s->sda_pin, true); master_latch(s->scl_pin, true);
    master_latch(s->sda_pin, false); master_latch(s->scl_pin, false);
}
static void master_stop(M5StopwatchSoftI2C *s)
{
    master_latch(s->scl_pin, false); master_latch(s->sda_pin, false);
    master_latch(s->scl_pin, true); master_latch(s->sda_pin, true);
}
static void master_bits(M5StopwatchSoftI2C *s, uint8_t byte)
{
    for (int bit = 7; bit >= 0; bit--) {
        master_latch(s->sda_pin, (byte >> bit) & 1);
        master_latch(s->scl_pin, true); master_latch(s->scl_pin, false);
    }
}
static bool master_write(M5StopwatchSoftI2C *s, uint8_t byte)
{
    master_bits(s, byte);
    master_latch(s->sda_pin, true); master_latch(s->scl_pin, true);
    bool ack = !master_read(s->sda_pin);
    master_latch(s->scl_pin, false);
    return ack;
}
static uint8_t master_receive(M5StopwatchSoftI2C *s)
{
    uint8_t value = 0;
    master_latch(s->sda_pin, true);
    for (unsigned bit = 0; bit < 8; bit++) {
        master_latch(s->scl_pin, true);
        value = (value << 1) | master_read(s->sda_pin);
        master_latch(s->scl_pin, false);
    }
    /* NACK the final byte. */
    master_latch(s->scl_pin, true); master_latch(s->scl_pin, false);
    return value;
}
static uint8_t read_register(M5StopwatchSoftI2C *s, uint8_t reg)
{
    master_start(s);
    assert(master_write(s, 0xb0)); assert(master_write(s, reg));
    master_start(s);
    assert(master_write(s, 0xb1));
    uint8_t value = master_receive(s);
    master_stop(s);
    return value;
}
static void write_register(M5StopwatchSoftI2C *s, uint8_t reg, uint8_t value)
{
    master_start(s);
    assert(master_write(s, 0xb0)); assert(master_write(s, reg));
    assert(master_write(s, value));
    master_stop(s);
}
static M5StopwatchSoftI2C *setup(I2CBus *bus, unsigned sda, unsigned scl)
{
    init_controller();
    bus->regs[0x10] = 0x23;
    bus->regs[0x44] = 0x9b;
    m5stopwatch_soft_i2c_init_pins(bus, sda, scl);
    M5StopwatchSoftI2C *s = soft_i2c_instance;
    assert(g_reset_listener_count[sda] <= 1 && !g_reset_listener_count[scl]);
    master_configure(s);
    assert(read_register(s, 0x10) == 0x23);
    write_register(s, 0x44, 0x77);
    return s;
}
static void assert_reset_state(M5StopwatchSoftI2C *s)
{
    assert(!s->hardware_active);
    assert(!s->active && !s->in_xfer && !s->read && s->state == SOFT_I2C_IDLE);
    assert(!s->ack_pending && !s->master_ack && !s->ack_step);
    assert(!s->bit && !s->shift && !s->rx);
    assert(s->sda == esp32_gpio_get_line(s->sda_pin));
    assert(s->scl == esp32_gpio_get_line(s->scl_pin));
    assert(g_ext_in & (1ULL << s->sda_pin));
    /* Do not overwrite reset's pad configuration or duplicate board wiring. */
    assert(!(g_open_drain & ((1ULL << s->sda_pin) | (1ULL << s->scl_pin))));
    assert(s->sda_pullup && s->scl_pullup && host_object_refs == 2);
    assert(s->sda_pullup->owner == s && s->scl_pullup->owner == s);
}
static void assert_handoff(M5StopwatchSoftI2C *s)
{
    m5stopwatch_soft_i2c_set_hardware_active_on_bus(s->bus);
    unsigned starts = s->bus->starts, sends = s->bus->sends;
    assert(s->hardware_active && !s->in_xfer && !s->active);
    master_start(s);
    assert(!master_write(s, 0xb0));
    master_stop(s);
    assert(s->bus->starts == starts && s->bus->sends == sends);
}
static void handoff_reset(unsigned sda, unsigned scl)
{
    I2CBus bus = {0};
    M5StopwatchSoftI2C *s = setup(&bus, sda, scl);
    assert_handoff(s);
    /* Model an independent hardware-controller owner, not a bridge transfer.
     * GPIO reset may re-enable the bridge but must not finish that owner. */
    assert(i2c_start_transfer(&bus, 0x58, 1) == 0 && bus.selected);
    unsigned starts = bus.starts, sends = bus.sends, receives = bus.receives;
    unsigned ends = bus.ends;
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert_reset_state(s);
    assert(bus.starts == starts && bus.sends == sends && bus.receives == receives);
    assert(bus.ends == ends && bus.selected);
    i2c_end_transfer(&bus); /* The independent owner finishes its own transfer. */
    assert(bus.regs[0x10] == 0x23 && bus.regs[0x44] == 0x77);
    master_configure(s);
    assert(read_register(s, 0x10) == 0x23 && read_register(s, 0x44) == 0x77);
    assert_handoff(s);
    for (unsigned i = 0; i < 2; i++) {
        esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
        assert_reset_state(s);
    }
    master_configure(s);
    assert(read_register(s, 0x10) == 0x23);
    puts("cold ACK/read -> hardware handoff -> GPIO reset -> ACK/read -> handoff PASS");
}
static void bridge_active_reset(bool receiving)
{
    I2CBus bus = {0};
    M5StopwatchSoftI2C *s = setup(&bus, 12, 11);
    master_start(s);
    if (receiving) {
        assert(master_write(s, 0xb0)); assert(master_write(s, 0x10));
        master_start(s); assert(master_write(s, 0xb1));
        assert(s->state == SOFT_I2C_RX && !s->sda);
    } else {
        /* Interrupt the address ACK while the bridge actively holds SDA. */
        master_bits(s, 0xb0);
        assert(s->state == SOFT_I2C_ACK_ADDR && s->ack_step == 1 && !s->sda);
    }
    assert(s->in_xfer && bus.selected);
    unsigned starts = bus.starts, sends = bus.sends, receives = bus.receives;
    unsigned ends = bus.ends;
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert_reset_state(s);
    assert(!bus.selected && bus.ends == ends + 1);
    assert(bus.starts == starts && bus.sends == sends && bus.receives == receives);
    assert(bus.regs[0x10] == 0x23 && bus.regs[0x44] == 0x77);
    master_configure(s);
    assert(read_register(s, 0x10) == 0x23 && read_register(s, 0x44) == 0x77);
    puts("active ACK/RX reset ends owned transfer once; registers/line samples retained PASS");
}
static void fresh_reset(bool external_low)
{
    init_controller();
    I2CBus bus = {0};
    m5stopwatch_soft_i2c_init_pins(&bus, 12, 11);
    M5StopwatchSoftI2C *s = soft_i2c_instance;
    assert(!(g_external_seen & (1ULL << 12)));
    if (external_low) { esp32_gpio_set_input(12, 0); }
    uint64_t seen = g_external_seen, external = g_ext_in;
    Esp32GpioBoardBias *sda_bias = s->sda_pullup, *scl_bias = s->scl_pullup;
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert(g_external_seen == seen && g_ext_in == external);
    assert(!s->active && !s->in_xfer && !s->hardware_active);
    assert(s->sda == esp32_gpio_get_line(12) && s->scl == esp32_gpio_get_line(11));
    assert(s->sda_pullup == sda_bias && s->scl_pullup == scl_bias && host_object_refs == 2);
    assert(bus.starts == 0 && bus.ends == 0 && bus.sends == 0 && bus.receives == 0);
    Esp32GpioPadSnapshot pad;
    assert(esp32_gpio_pad_snapshot(&controller, 12, &pad));
    assert(pad.external_seen == external_low && pad.bias_up_count == 1);
    if (external_low) { assert(!esp32_gpio_get_line(12)); }
    puts("fresh reset preserves absent/independent external SDA source and board bias PASS");
}
static void classic_unchanged(void)
{
    host_s3 = false;
    esp32_gpio_init(OBJECT(&controller));
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    I2CBus bus = {0};
    m5stopwatch_soft_i2c_init_pins(&bus, 21, 22);
    assert(!g_reset_listener_count[21] && !g_reset_listener_count[22]);
    assert(esp32_gpio_get_line(21) == 1 && esp32_gpio_get_line(22) == 1);
    puts("classic reset registration and legacy idle levels unchanged PASS");
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "cores3")) { handoff_reset(12, 11); }
    else if (!strcmp(argv[1], "stopwatch")) { handoff_reset(47, 48); }
    else if (!strcmp(argv[1], "ack")) { bridge_active_reset(false); }
    else if (!strcmp(argv[1], "rx")) { bridge_active_reset(true); }
    else if (!strcmp(argv[1], "fresh")) { fresh_reset(false); }
    else if (!strcmp(argv[1], "external-low")) { fresh_reset(true); }
    else if (!strcmp(argv[1], "classic")) { classic_unchanged(); }
    else { abort(); }
    return 0;
}
