"""Exercise the actual peer-input and receiver code with an independent source."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    source = args.source.read_text()
    begin = source.index('static uint64_t g_peer_drive_mask, g_peer_drive_high;')
    end = source.index('static uint32_t g_iomux_regs', begin)
    declarations = source[begin:end]
    attach = function(source, 'Esp32GpioPeerInput *esp32_gpio_attach_peer_input(')
    drive = function(source, 'void esp32_gpio_drive_peer_input_deferred(')
    receiver = function(source, 'static uint64_t gpio_legacy_line64(void)\n{')
    code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#define GPIO_NPINS 54
typedef struct Esp32GpioState { unsigned unused; } Esp32GpioState;
typedef struct Esp32GpioPeerInput Esp32GpioPeerInput;
typedef struct Error { bool set; } Error;
static Esp32GpioState gpio;
static Esp32GpioState *g_gpio_device = &gpio;
static uint64_t g_external_seen, g_ext_in = UINT64_MAX;
static uint64_t g_open_drain, g_force_mask, g_force_level, out, en;
static uint64_t gpio_out64(void) { return out; }
static uint64_t gpio_en64(void) { return en; }
static bool gpio_pad_valid(Esp32GpioState *s, unsigned pin) {
    return s == &gpio && pin < GPIO_NPINS;
}
static void error_setg(Error **error, const char *format, unsigned pin) {
    static Error failure = { true };
    *error = &failure;
}
''' + declarations + attach + '\n' + drive + '\n' + receiver + r'''
int main(void) {
    Error *error = NULL;
    Esp32GpioPeerInput *peer = esp32_gpio_attach_peer_input(&gpio, 15, &error);
    assert(peer && !error);
    assert(!esp32_gpio_attach_peer_input(&gpio, 15, &error) && error->set);
    uint64_t sda = UINT64_C(1) << 15;
    assert(gpio_legacy_line64() & sda);
    esp32_gpio_drive_peer_input_deferred(peer, 0);
    assert(!(gpio_legacy_line64() & sda));
    assert(g_ext_in == UINT64_MAX && !g_external_seen);
    g_external_seen |= sda;
    g_ext_in &= ~sda;
    esp32_gpio_drive_peer_input_deferred(peer, -1);
    assert(!(gpio_legacy_line64() & sda));
    assert(g_external_seen == sda && !(g_ext_in & sda));
    esp32_gpio_drive_peer_input_deferred(peer, 1);
    assert(!(gpio_legacy_line64() & sda));
    g_ext_in |= sda;
    assert(gpio_legacy_line64() & sda);
    esp32_gpio_drive_peer_input_deferred(peer, -1);
    assert(gpio_legacy_line64() & sda);
    assert(g_external_seen == sda && g_ext_in == UINT64_MAX);
    puts("PASS actual peer input and legacy receiver ownership");
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='m5-plus2-peer-') as temp:
        test = Path(temp) / 'probe.c'
        executable = test.with_suffix('')
        test.write_text(code)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', str(test), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    main()
