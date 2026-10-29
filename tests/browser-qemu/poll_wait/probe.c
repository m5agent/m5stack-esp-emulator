/* SPDX-License-Identifier: MIT
 * Real SDK poll/pipe/pthread controls, without a guest or QEMU runtime.
 * The generated include is the actual branch from patch 0015.
 */
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <emscripten/emscripten.h>
#include <emscripten/threading.h>

typedef unsigned guint;
typedef struct pollfd GPollFD;
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define g_poll poll
#include "actual-poll.inc"

static int pipe_fds[2];
static void *writer(void *unused)
{
    emscripten_thread_sleep(15);
    assert(write(pipe_fds[1], "x", 1) == 1);
    return NULL;
}

int main(void)
{
    double start, ignored_ms, finite_ms, nonblocking_ms, ready_ms, wake_ms[2];
    GPollFD fd;
    char byte;
    pthread_t thread;

    /* Preserve this negative control: the pinned SDK ignores the deadline. */
    start = emscripten_get_now();
    assert(poll(NULL, 0, 30) == 0);
    ignored_ms = emscripten_get_now() - start;
    assert(ignored_ms < 20);
    start = emscripten_get_now();
    assert(qemu_poll_ns(NULL, 0, 30000000) == 0);
    finite_ms = emscripten_get_now() - start;
    assert(finite_ms >= 28 && finite_ms < 1000);

    assert(pipe(pipe_fds) == 0);
    fd = (GPollFD) { .fd = pipe_fds[0], .events = POLLIN };
    start = emscripten_get_now();
    assert(qemu_poll_ns(&fd, 1, 0) == 0);
    nonblocking_ms = emscripten_get_now() - start;
    assert(nonblocking_ms < 20);
    assert(write(pipe_fds[1], "r", 1) == 1);
    start = emscripten_get_now();
    assert(qemu_poll_ns(&fd, 1, 1000000000) == 1 && (fd.revents & POLLIN));
    ready_ms = emscripten_get_now() - start;
    assert(ready_ms < 20 && read(pipe_fds[0], &byte, 1) == 1 && byte == 'r');

    for (int control = 0; control < 2; control++) {
        assert(pthread_create(&thread, NULL, writer, NULL) == 0);
        start = emscripten_get_now();
        assert(qemu_poll_ns(&fd, 1, control ? -1 : 1000000000) == 1);
        wake_ms[control] = emscripten_get_now() - start;
        assert(wake_ms[control] >= 10 && wake_ms[control] < 1000);
        assert(pthread_join(thread, NULL) == 0);
        assert(read(pipe_fds[0], &byte, 1) == 1 && byte == 'x');
    }
    close(pipe_fds[0]); close(pipe_fds[1]);
    printf("M5_POLL_WAIT {\"sdk_ignored_timeout_ms\":%.3f,\"finite_ms\":%.3f,"
           "\"nonblocking_ms\":%.3f,\"ready_ms\":%.3f,"
           "\"finite_wake_ms\":%.3f,\"infinite_wake_ms\":%.3f,\"controls\":6}\n",
           ignored_ms, finite_ms, nonblocking_ms, ready_ms, wake_ms[0], wake_ms[1]);
    return 0;
}
