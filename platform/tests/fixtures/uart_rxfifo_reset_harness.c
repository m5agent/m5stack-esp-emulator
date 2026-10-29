/* Exact UART/Fifo8/SCS algorithms are inserted at the marked boundaries.
 * The deterministic clock, timer handles, IRQ sink and character backend are
 * host plumbing; no guest execution or physical-device behavior is claimed. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#define REG32(name, addr) enum { A_##name = (addr), R_##name = (addr) / 4 };
#define FIELD(reg, name, shift, length) \
    enum { R_##reg##_##name##_SHIFT = (shift), \
           R_##reg##_##name##_MASK = ((1u << (length)) - 1) << (shift) };
#define FIELD_EX32(value, reg, name) \
    (((value) & R_##reg##_##name##_MASK) >> R_##reg##_##name##_SHIFT)
#define FIELD_DP32(value, reg, name, field) \
    (((value) & ~R_##reg##_##name##_MASK) | \
     (((uint32_t)(field) << R_##reg##_##name##_SHIFT) & R_##reg##_##name##_MASK))
#define OBJECT_CHECK(type, obj, name) ((type *)(obj))
#define OBJECT_GET_CLASS(type, obj, name) ((type *)&s3_class)
#define OBJECT_CLASS_CHECK(type, klass, name) ((type *)(klass))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define g_new(type, count) ((type *)malloc(sizeof(type) * (count)))
#define g_free free
#define QEMU_CLOCK_VIRTUAL 0
#define NANOSECONDS_PER_SECOND 1000000000LL
#define G_IO_OUT 1
#define G_IO_HUP 2
#define FALSE 0
typedef int gboolean;
typedef unsigned guint;
typedef int GIOCondition;
typedef int QEMUChrEvent;
typedef uint64_t hwaddr;
typedef struct { int unused; } SysBusDevice;
typedef struct { int unused; } SysBusDeviceClass;
typedef struct { int unused; } MemoryRegion;
typedef struct { int unused; } MemoryRegionOps;
typedef struct { int unused; } VMStateDescription;
typedef struct { int unused; } DeviceState;
typedef struct { int unused; } Error;
typedef void (*DeviceRealize)(DeviceState *, Error **);
typedef int *qemu_irq;
typedef struct { int64_t expire_time; } QEMUTimer;
typedef struct { unsigned accepts; } CharBackend;
static int64_t now_ns;
static int64_t qemu_clock_get_ns(int clock) { return now_ns; }
static void timer_del(QEMUTimer *timer) { timer->expire_time = -1; }
static void timer_mod_ns(QEMUTimer *timer, int64_t value) { timer->expire_time = value; }
static void qemu_set_irq(qemu_irq irq, int level) { *irq = level; }
static void qemu_chr_fe_accept_input(CharBackend *chr) { chr->accepts++; }
static int qemu_chr_fe_backend_open(CharBackend *chr) { return 0; }
static int qemu_chr_fe_write(CharBackend *chr, const uint8_t *data, int size) { return size; }
static unsigned qemu_chr_fe_add_watch(CharBackend *chr, int cond, void *fn, void *opaque) { return 0; }
static void error_report(const char *fmt, ...) { assert(!"unexpected UART model error"); }
static void m5_unit_uart_tx(void *uart, uint8_t byte) { }
/* REAL_HEADERS */
static ESP32S3UARTClass s3_class;
/* REAL_FIFO */
/* REAL_PARENT */
/* REAL_S3 */

#define SCS_MAX_PACKET 256
typedef struct {
    ESP32UARTState *uart;
    uint64_t disconnected_rx_packets;
} M5ScsServoState;
static bool scs_rx_connected(void) { return true; }
/* REAL_SCS_SEND */

static ESP32S3UARTState uart;
static int irq;
static M5ScsServoState peer;
static const uint32_t rx_interrupts = R_UART_INT_ENA_RXFIFO_FULL_MASK |
                                      R_UART_INT_ENA_RXFIFO_TOUT_MASK;
static void setup(void)
{
    memset(&uart, 0, sizeof(uart));
    irq = 0; now_ns = 0;
    uart.parent.irq = &irq;
    uart.parent.baud_rate = 1000000;
    uart.parent.baud_scale = 1;
    timer_del(&uart.parent.rx_timeout_timer);
    timer_del(&uart.parent.throttle_timer);
    fifo8_create(&uart.parent.rx_fifo, UART_FIFO_LENGTH);
    fifo8_create(&uart.parent.tx_fifo, UART_FIFO_LENGTH);
    s3_class.parent_uart_write = uart_write;
    s3_class.parent_uart_read = uart_read;
    peer.uart = &uart.parent;
    esp32s3_uart_write(&uart, A_ESP32S3_UART_MEM_CONF, 10u << 17, 4);
    esp32s3_uart_write(&uart, A_ESP32S3_UART_CONF1, (1u << 23) | 120, 4);
    esp32s3_uart_write(&uart, A_UART_INT_ENA, rx_interrupts, 4);
}
static void advance_to(int64_t target)
{
    now_ns = target;
    if (uart.parent.rx_timeout_timer.expire_time >= 0 &&
        uart.parent.rx_timeout_timer.expire_time <= now_ns) {
        timer_del(&uart.parent.rx_timeout_timer);
        uart_rx_timeout_timer_cb(&uart.parent);
    }
    if (uart.parent.throttle_timer.expire_time >= 0 &&
        uart.parent.throttle_timer.expire_time <= now_ns) {
        timer_del(&uart.parent.throttle_timer);
        uart_throttle_timer_cb(&uart.parent);
    }
}
static void rx_reset_pulse(uint32_t framing)
{
    /* IDF 4.4.7 ESP32-S3 uart_ll_rxfifo_rst writes CONF0 RXFIFO_RST
     * bit 17 to 1, then 0, preserving every other configuration bit. */
    esp32s3_uart_write(&uart, A_ESP32S3_UART_CONF0, framing | (1u << 17), 4);
    esp32s3_uart_write(&uart, A_ESP32S3_UART_CONF0, framing, 4);
}
static void assert_read_reply(void)
{
    const uint8_t data[] = { 1, 0xcc }; /* raw position 460 */
    const uint8_t expected[] = { 0xff, 0xff, 1, 4, 0, 1, 0xcc, 0x2d };
    scs_send(&peer, 1, 0, data, sizeof(data));
    assert(fifo8_num_used(&uart.parent.rx_fifo) == sizeof(expected));
    assert(!irq); /* Eight bytes are below the configured full threshold. */
    assert(uart.parent.rx_timeout_timer.expire_time > now_ns);
    advance_to(uart.parent.rx_timeout_timer.expire_time);
    assert(irq && (uart.parent.reg[R_UART_INT_ST] & R_UART_INT_ST_RXFIFO_TOUT_MASK));
    for (unsigned i = 0; i < sizeof(expected); i++) {
        assert(FIELD_EX32(esp32s3_uart_read(&uart, A_UART_STATUS, 4),
                          UART_STATUS, RXFIFO_CNT) == sizeof(expected) - i);
        assert(esp32s3_uart_read(&uart, A_UART_FIFO, 1) == expected[i]);
    }
    esp32s3_uart_write(&uart, A_UART_INT_CLR, R_UART_INT_CLR_RXFIFO_TOUT_MASK, 4);
    assert(!irq && !uart.parent.rxfifo_tout && fifo8_is_empty(&uart.parent.rx_fifo));
}
static void flush_ack_read(void)
{
    setup();
    scs_send(&peer, 1, 0, NULL, 0); /* Real six-byte unicast WRITE ACK. */
    assert(fifo8_num_used(&uart.parent.rx_fifo) == 6);
    assert(!irq); /* ISR has not moved the ACK to the IDF driver ring. */
    uint32_t framing = 0x1cu;
    rx_reset_pulse(framing);
    assert(fifo8_num_used(&uart.parent.rx_fifo) == 0);
    assert(uart.parent.reg[R_UART_CONF0] == framing);
    assert_read_reply();
    puts("stale SCS ACK -> IDF RXFIFO pulse -> exact ReadPos reply PASS");
}
static void timeout_throttle(void)
{
    setup();
    const uint8_t junk[UART_FIFO_LENGTH] = { 0x55 };
    esp32_uart_inject_rx(&uart.parent, junk, sizeof(junk));
    assert(irq && uart.parent.throttle_rx);
    assert(uart.parent.rx_timeout_timer.expire_time >= 0);
    assert(uart.parent.throttle_timer.expire_time >= 0);
    advance_to(uart.parent.rx_timeout_timer.expire_time);
    assert(uart.parent.rxfifo_tout);
    /* Hold a pending receive throttle independently of its original deadline. */
    uart.parent.throttle_rx = true;
    timer_mod_ns(&uart.parent.throttle_timer, now_ns + 10000000);
    fifo8_push(&uart.parent.tx_fifo, 0xa5);
    uint32_t mask = uart.parent.reg[R_UART_INT_ENA], framing = 0x1cu;
    uint32_t conf1 = uart.conf1, baud = uart.parent.baud_rate;
    unsigned accepts = uart.parent.chr.accepts;
    rx_reset_pulse(framing);
    assert(fifo8_is_empty(&uart.parent.rx_fifo));
    assert(!uart.parent.rxfifo_tout && !uart.parent.throttle_rx && !irq);
    assert(uart.parent.rx_timeout_timer.expire_time == -1);
    assert(uart.parent.throttle_timer.expire_time == -1);
    assert(uart.parent.reg[R_UART_INT_ENA] == mask && uart.conf1 == conf1);
    assert(uart.parent.reg[R_UART_CONF0] == framing && uart.parent.baud_rate == baud);
    assert(fifo8_num_used(&uart.parent.tx_fifo) == 1 && fifo8_peek(&uart.parent.tx_fifo) == 0xa5);
    assert(uart.parent.chr.accepts > accepts);
    advance_to(now_ns + 100000000);
    assert(!irq && !uart.parent.rxfifo_tout);
    assert_read_reply();
    puts("RX timers/IRQ cleared; TX/config/interrupt masks retained PASS");
}
static void unrelated(void)
{
    setup();
    scs_send(&peer, 1, 0, NULL, 0);
    int64_t timeout = uart.parent.rx_timeout_timer.expire_time;
    esp32s3_uart_write(&uart, A_ESP32S3_UART_CONF0, 0x1cu, 4);
    assert(fifo8_num_used(&uart.parent.rx_fifo) == 6);
    assert(uart.parent.rx_timeout_timer.expire_time == timeout);
    /* The generic/classic UART path is outside this S3-only patch. */
    uart_write(&uart.parent, A_UART_CONF0, (1u << 17), 4);
    assert(fifo8_num_used(&uart.parent.rx_fifo) == 6);
    puts("unrelated CONF0 and classic parent behavior retained PASS");
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "flush-ack-read")) { flush_ack_read(); }
    else if (!strcmp(argv[1], "timeout-throttle")) { timeout_throttle(); }
    else if (!strcmp(argv[1], "reply-irq-drain")) {
        setup(); assert_read_reply();
        puts("real SCS response -> parent FIFO -> RX timeout IRQ -> MMIO drain PASS");
    } else if (!strcmp(argv[1], "unrelated")) { unrelated(); }
    else { abort(); }
    return 0;
}
