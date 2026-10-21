/*
 * Headless CardputerZero framebuffer compatibility shim.
 *
 * panel-mipi-dbi's FBIOBLANK path waits on the emulated SPI clock transition.
 * The QEMU test does not need to power the physical panel down, so suppress
 * only FBIOBLANK and pass every other ioctl through.
 *
 * SPDX-License-Identifier: MIT
 */
#define _GNU_SOURCE
#include <stdarg.h>

#define FBIOBLANK 0x4611
#define RTLD_NEXT ((void *)-1L)

typedef int (*ioctl_fn)(int, unsigned long, void *);
extern void *dlsym(void *handle, const char *symbol);

int ioctl(int fd, unsigned long request, ...)
{
    static ioctl_fn real_ioctl;
    va_list args;
    void *argument;

    va_start(args, request);
    argument = va_arg(args, void *);
    va_end(args);

    if (request == FBIOBLANK) {
        return 0;
    }
    if (!real_ioctl) {
        real_ioctl = (ioctl_fn)dlsym(RTLD_NEXT, "ioctl");
    }
    return real_ioctl(fd, request, argument);
}
