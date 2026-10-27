/* I2C method shims support the real bridge's initialization/line callbacks.
 * Their return values are not endpoint or protocol validation. */
typedef struct I2CBus { unsigned calls; } I2CBus;
static int i2c_start_transfer(I2CBus *s, int addr, int read) { s->calls++; return 0; }
static void i2c_end_transfer(I2CBus *s) { s->calls++; }
static int i2c_send(I2CBus *s, int byte) { s->calls++; return 0; }
static int i2c_recv(I2CBus *s) { s->calls++; return 0xff; }
static void i2c_nack(I2CBus *s) { s->calls++; }

/* BRIDGE_SOURCE */

/* Digital portion of fixed M5GFX 9bcedf4 pinMode(): IOMUX receiver/function,
 * PAD_DRIVER, latch-high for input, ENABLE and GPIO256 route, in that order.
 * RTC deinit/pull calls are outside this narrow nominal digital regression. */
static void probe_pinmode(unsigned n, unsigned mode)
{
    uint32_t value = g_iomux_regs[n];
    value &= ~((1u << 8) | (1u << 7) | (1u << 3) | (1u << 2));
    if (mode == 1) { value |= (1u << 7) | (1u << 2); }
    if (mode == 2) { value |= (1u << 8) | (1u << 3); }
    value = (value & ~(7u << 12)) | (1u << 12) | (1u << 9);
    esp32_gpio_iomux_write(&controller, 4 + n * 4, value, 4);
    uint32_t cfg = g_regs[(0x74 + n * 4) / 4];
    gpio_write(0x74 + n * 4, mode ? cfg | (1u << 2) : cfg & ~(1u << 2));
    if (mode) { gpio_write(n < 32 ? 0x08 : 0x14, 1u << (n & 31)); }
    gpio_write(n < 32 ? 0x24 : 0x30, 1u << (n & 31));
    gpio_write(0x554 + n * 4, 256);
}
static unsigned probe_read(unsigned n)
{
    uint32_t value = esp32_gpio_read(&controller, n < 32 ? 0x3c : 0x40, 4);
    return !!(value & (1u << (n & 31)));
}
static void probe_latch(unsigned n, bool high)
{ gpio_write((n < 32 ? 0x08 : 0x14) + (high ? 0 : 4), 1u << (n & 31)); }
static Esp32GpioPadSnapshot probe_snapshot(unsigned n)
{
    Esp32GpioPadSnapshot value;
    assert(esp32_gpio_pad_snapshot(&controller, n, &value));
    return value;
}
static void assert_owned_bias(M5StopwatchSoftI2C *s)
{
#if WITH_PULLUPS
    assert(s->sda_pullup && s->scl_pullup && s->sda_pullup != s->scl_pullup);
    assert(s->sda_pullup->owner == s && s->scl_pullup->owner == s);
    assert(s->sda_pullup->gpio == &controller && s->scl_pullup->gpio == &controller);
    assert(probe_snapshot(s->sda_pin).bias_up_count == 1);
    assert(probe_snapshot(s->scl_pin).bias_up_count == 1);
    assert(host_object_refs == 2);
#else
    assert(!g_board_biases && host_object_refs == 0);
#endif
}
static void s3_probe(unsigned sda, unsigned scl)
{
    init_controller();
    I2CBus bus = {0};
    m5stopwatch_soft_i2c_init_pins(&bus, sda, scl);
    M5StopwatchSoftI2C *s = soft_i2c_instance;
    assert(s && s->bus == &bus);
    assert_owned_bias(s);
    probe_pinmode(scl, 0); probe_pinmode(sda, 0);
    for (unsigned i = 0; i < 8; i++) {
        probe_latch(scl, false); probe_latch(sda, false);
        probe_latch(scl, true); probe_latch(sda, true);
    }
    unsigned reads = 0;
    probe_latch(scl, false); reads = (reads << 1) | probe_read(scl);
    probe_latch(sda, false); reads = (reads << 1) | probe_read(sda);
    probe_pinmode(scl, 1);
    Esp32GpioPadSnapshot down = probe_snapshot(scl);
    reads = (reads << 1) | probe_read(scl);
    probe_pinmode(scl, 2); probe_pinmode(sda, 1);
    reads = (reads << 1) | probe_read(sda);
    probe_pinmode(sda, 2);
    printf("probe=0x%x known=%u conflict=%u board_up=%u external=%u ie=%u\n",
           reads, down.known, down.conflict, down.bias_up_count, down.external_seen, down.fun_ie);
    assert(down.fun_ie && !down.external_seen && !down.force_enabled);
#if WITH_PULLUPS
    assert(reads == 3 && !down.known && down.conflict);
    assert(down.source_mask & ESP32_GPIO_PAD_SOURCE_BOARD_UP);
    assert(down.source_mask & ESP32_GPIO_PAD_SOURCE_IOMUX_DOWN);
#else
    assert(reads == 1 && down.known && !down.level && !down.conflict);
#endif
    m5stopwatch_soft_i2c_set_hardware_active_on_bus(&bus);
    assert(s->hardware_active); assert_owned_bias(s);
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert_owned_bias(s);
#if WITH_PULLUPS
    /* The harness removes handles to verify independent ownership. There is
     * no product hot-unplug API; legacy bridge/listener lifetime is process. */
    esp32_gpio_remove_board_bias(s->sda_pullup);
    assert(probe_snapshot(scl).bias_up_count == 1 && host_object_refs == 1);
    esp32_gpio_remove_board_bias(s->scl_pullup);
    assert(!g_board_biases && host_object_refs == 0);
#endif
}
static void core2_probe(void)
{
    host_s3 = false;
    esp32_gpio_init(OBJECT(&controller));
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    I2CBus bus = {0};
    m5stopwatch_soft_i2c_init_pins(&bus, 21, 22);
    assert_owned_bias(soft_i2c_instance);
    assert(probe_read(21) == 1 && probe_read(22) == 1);
    gpio_write(0x24, 1u << 21);
    assert(probe_read(21) == 0);
    gpio_write(0x08, 1u << 21);
    assert(probe_read(21) == 1);
    puts("core2 high=1,1 driven_low=0 released=1");
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "cores3")) { s3_probe(12, 11); }
    else if (!strcmp(argv[1], "stopwatch")) { s3_probe(47, 48); }
    else if (!strcmp(argv[1], "core2")) { core2_probe(); }
    else { abort(); }
    return 0;
}
