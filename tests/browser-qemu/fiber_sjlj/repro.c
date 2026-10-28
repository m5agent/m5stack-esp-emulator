#include <assert.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <emscripten.h>
#include <emscripten/fiber.h>
#include <emscripten/stack.h>
#include <ffi.h>

#ifndef M5_RESTORE_AFTER_LONGJMP
#define M5_RESTORE_AFTER_LONGJMP 0
#endif
EM_JS(void, m5_restore_stack, (uintptr_t saved_sp), {
    stackRestore(saved_sp);
});

#define ITERATIONS 1000
typedef struct {
    uintptr_t before_setjmp;
    uintptr_t before_call;
    uintptr_t helper_entry;
    uintptr_t before_fiber_swap;
    uintptr_t fiber_entry;
    uintptr_t after_fiber_swap;
    uintptr_t before_longjmp;
    uintptr_t before_restore;
    uintptr_t after_longjmp;
    uintptr_t helper_buffer;
    unsigned helper_calls;
    unsigned fiber_visits;
} Record;
static Record records[2][ITERATIONS];
static jmp_buf jump_env;
static unsigned current_lane;
static unsigned current_iteration;
static unsigned callback_count;
static volatile unsigned sink;
static unsigned fiber_visit_count;
static emscripten_fiber_t leader_fiber, worker_fiber;
static void *worker_c_stack, *worker_async_stack, *leader_async_stack;
static ffi_cif cif;
static ffi_type *argument_types[2] = {&ffi_type_uint32, &ffi_type_uint32};

__attribute__((noinline)) static void worker_entry(void *unused)
{
    volatile uint8_t frame[128];
    (void)unused;
    for (;;) {
        frame[0] = (uint8_t)current_iteration;
        records[current_lane][current_iteration].fiber_entry = emscripten_stack_get_current();
        records[current_lane][current_iteration].fiber_visits++;
        ++fiber_visit_count;
        sink += frame[0];
        emscripten_fiber_swap(&worker_fiber, &leader_fiber);
    }
}

__attribute__((noinline)) static void jump_helper(uint32_t lane, uint32_t iteration)
{
    volatile uint8_t frame[608];
    assert(lane == current_lane && iteration == current_iteration);
    for (unsigned index = 0; index < sizeof(frame); ++index) {
        frame[index] = (uint8_t)(iteration + index);
    }
    records[lane][iteration].helper_entry = emscripten_stack_get_current();
    records[lane][iteration].helper_buffer = (uintptr_t)&frame[0];
    records[lane][iteration].helper_calls++;
    ++callback_count;
    sink += frame[iteration % sizeof(frame)];
    records[lane][iteration].before_fiber_swap = emscripten_stack_get_current();
    emscripten_fiber_swap(&leader_fiber, &worker_fiber);
    records[lane][iteration].after_fiber_swap = emscripten_stack_get_current();
    records[lane][iteration].before_longjmp = emscripten_stack_get_current();
    longjmp(jump_env, 1);
}

__attribute__((noinline)) static void call_direct(void)
{
    jump_helper(current_lane, current_iteration);
    abort();
}

__attribute__((noinline)) static void call_ffi(void)
{
    uint32_t lane = current_lane;
    uint32_t iteration = current_iteration;
    void *arguments[2] = {&lane, &iteration};
    ffi_call(&cif, FFI_FN(jump_helper), NULL, arguments);
    abort();
}

__attribute__((noinline)) static void run_lane(unsigned lane)
{
    current_lane = lane;
    for (current_iteration = 0; current_iteration < ITERATIONS; ++current_iteration) {
        const uintptr_t saved_sp = emscripten_stack_get_current();
        records[current_lane][current_iteration].before_setjmp = saved_sp;
        switch (setjmp(jump_env)) {
        case 0:
            records[current_lane][current_iteration].before_call = emscripten_stack_get_current();
            if (current_lane == 0) {
                call_direct();
            } else {
                call_ffi();
            }
            abort();
        case 1:
            records[current_lane][current_iteration].before_restore = emscripten_stack_get_current();
#if M5_RESTORE_AFTER_LONGJMP
            m5_restore_stack(saved_sp);
#endif
            records[current_lane][current_iteration].after_longjmp = emscripten_stack_get_current();
            break;
        default:
            abort();
        }
    }
}

int main(void)
{
    worker_c_stack = malloc(1024 * 1024);
    worker_async_stack = malloc(1024 * 1024);
    leader_async_stack = malloc(1024 * 1024);
    assert(worker_c_stack && worker_async_stack && leader_async_stack);
    emscripten_fiber_init_from_current_context(&leader_fiber, leader_async_stack, 1024 * 1024);
    emscripten_fiber_init(&worker_fiber, worker_entry, NULL,
                        worker_c_stack, 1024 * 1024, worker_async_stack, 1024 * 1024);
    assert(ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 2, &ffi_type_void, argument_types) == FFI_OK);
    printf("M5_SETJMP_START {\"iterations\":%u,\"stack_base\":%" PRIuPTR ",\"stack_end\":%" PRIuPTR "}\n",
           ITERATIONS, emscripten_stack_get_base(), emscripten_stack_get_end());
    run_lane(0);
    run_lane(1);
    unsigned restore_mismatches = 0, entry_drift = 0, bad_callbacks = 0;
    for (unsigned lane = 0; lane < 2; ++lane) {
        for (unsigned index = 0; index < ITERATIONS; ++index) {
            Record *record = &records[lane][index];
            restore_mismatches += record->after_longjmp != record->before_setjmp;
            entry_drift += record->before_setjmp != records[lane][0].before_setjmp;
            bad_callbacks += record->helper_calls != 1 || record->fiber_visits != 1;
            printf("M5_SETJMP_ROW {\"lane\":%u,\"iteration\":%u,\"before_setjmp\":%" PRIuPTR ",\"before_call\":%" PRIuPTR ",\"helper_entry\":%" PRIuPTR ",\"before_fiber_swap\":%" PRIuPTR ",\"fiber_entry\":%" PRIuPTR ",\"after_fiber_swap\":%" PRIuPTR ",\"before_longjmp\":%" PRIuPTR ",\"before_restore\":%" PRIuPTR ",\"after_longjmp\":%" PRIuPTR ",\"helper_buffer\":%" PRIuPTR ",\"helper_calls\":%u,\"fiber_visits\":%u}\n",
                   lane, index, record->before_setjmp, record->before_call,
                   record->helper_entry, record->before_fiber_swap, record->fiber_entry,
                   record->after_fiber_swap, record->before_longjmp,
                   record->before_restore, record->after_longjmp, record->helper_buffer, record->helper_calls,
                   record->fiber_visits);
        }
    }
    printf("M5_SETJMP_DONE {\"restore_mismatches\":%u,\"entry_drift\":%u,\"bad_callbacks\":%u,\"callback_count\":%u,\"fiber_visit_count\":%u,\"sink\":%u}\n",
           restore_mismatches, entry_drift, bad_callbacks, callback_count, fiber_visit_count, sink);
    free(worker_c_stack);
    free(worker_async_stack);
    free(leader_async_stack);
    unsigned result = restore_mismatches || entry_drift || bad_callbacks ||
                      callback_count != 2 * ITERATIONS || fiber_visit_count != 2 * ITERATIONS;
    printf("M5_SETJMP_RESULT {\"compat\":%d,\"result\":%u}\n",
           M5_RESTORE_AFTER_LONGJMP, result);
    /* Preserve the C result above; explicitly complete normal libc teardown. */
    exit(0);
}
