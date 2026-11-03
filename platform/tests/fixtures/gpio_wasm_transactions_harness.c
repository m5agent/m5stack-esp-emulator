/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host observation/setup only; model algorithms are inserted by exact patch replay. */

/* Extra host-only observation around the actual source replay. */
static uint64_t observation_hash = UINT64_C(1469598103934665603);
static uint64_t observation_events;
static void observe_bytes(const void *data, size_t size)
{
    Esp32GpioPadSnapshot normalized;
    if (test_normalize_timestamp && size == sizeof(normalized)) {
        normalized = *(const Esp32GpioPadSnapshot *)data;
        normalized.at_ns = 0; /* Hash facts separately from intentional time policy. */
        data = &normalized;
    }
    const unsigned char *p = data;
    for (size_t i = 0; i < size; i++) {
        observation_hash ^= p[i]; observation_hash *= UINT64_C(1099511628211);
    }
}
static void observe_snapshot(const Esp32GpioPadSnapshot *s)
{
    assert(s->at_ns == host_now_ns);
    observe_bytes(s, sizeof(*s));
}
static void observe_event(void *opaque, const Esp32GpioPadEvent *event)
{
    assert(event->after.pin == (uintptr_t)opaque);
    assert(event->before.at_ns <= host_now_ns);
    observe_bytes(&event->cause, sizeof(event->cause));
    observe_bytes(&event->change_mask, sizeof(event->change_mask));
    observe_bytes(&event->commit_sequence, sizeof(event->commit_sequence));
    observe_bytes(&event->before, sizeof(event->before));
    observe_snapshot(&event->after);
    observation_events++;
}
static void observe_lines_and_pads(void)
{
    uint64_t line = gpio_line64();
    observe_bytes(&line, sizeof(line));
    for (int n = -1; n <= GPIO_NPINS; n++) {
        int level = esp32_gpio_get_line(n);
        assert(level == (n < 0 || n >= GPIO_NPINS ? 1 : !!(line & BIT(n))));
        observe_bytes(&level, sizeof(level));
    }
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        Esp32GpioPadSnapshot state;
        bool valid = esp32_gpio_pad_snapshot(&controller, n, &state);
        assert(valid == gpio_pad_valid(&controller, n));
        observe_bytes(&valid, sizeof(valid));
        if (valid) { observe_snapshot(&state); }
    }
}
static int differential_grid(bool s3)
{
    host_s3 = s3;
    host_now_ns = 1000000;
    esp32_gpio_init(OBJECT(&controller));
    if (s3) { esp32s3_gpio_pad_aux_init(&controller, &system_mem, 0x60008400); }
    Esp32GpioPadObserver *observers[GPIO_NPINS] = { 0 };
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        if (!gpio_pad_valid(&controller, n)) { continue; }
        Error *err = NULL;
        Esp32GpioPadSnapshot initial;
        observers[n] = esp32_gpio_observe_pad(&controller, n, observe_event,
                            (void *)(uintptr_t)n, &initial, &err);
        assert(observers[n] && !err);
        observe_snapshot(&initial);
    }
    observe_lines_and_pads();
    static unsigned owner_up, owner_down;
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        if (!gpio_pad_valid(&controller, n)) { continue; }
        pin = n;
        Esp32GpioBoardBias *up = NULL, *down = NULL;
        for (unsigned step = 0; step < 22; step++) {
            host_now_ns += 101;
            Error *err = NULL;
            uint32_t mux_addr = s3 ? 4 + pin * 4 : classic_iomux_offset[pin];
            uint32_t mux_gpio = (s3 ? 1u : 2u) << 12;
            switch (step) {
            case 0: route(256); break;
            case 1: esp32_gpio_iomux_write(&controller, mux_addr, mux_gpio | BIT(9), 4); break;
            case 2: latch(false); break;
            case 3: output_enable(true); break;
            case 4: latch(true); break;
            case 5: esp32_gpio_set_open_drain(pin, true); break;
            case 6: esp32_gpio_set_input(pin, 0); break;
            case 7: esp32_gpio_set_input(pin, 1); break;
            case 8: esp32_gpio_force_line(pin, 0); break;
            case 9: esp32_gpio_force_line(pin, 1); break;
            case 10: output_enable(false); break;
            case 11: up = esp32_gpio_add_board_bias(&controller, pin, ESP32_GPIO_BIAS_PULL_UP, &owner_up, &err); assert(up && !err); break;
            case 12: down = esp32_gpio_add_board_bias(&controller, pin, ESP32_GPIO_BIAS_PULL_DOWN, &owner_down, &err); assert(down && !err); break;
            case 13: esp32_gpio_iomux_write(&controller, mux_addr, mux_gpio | BIT(9) | BIT(7) | BIT(8), 4); break;
            case 14: route(256 | BIT(9) | BIT(10) | BIT(11)); break;
            case 15: gpio_write((s3 ? 0x74 : 0x88) + pin * 4, BIT(2) | (3u << 7) | BIT(13)); break;
            case 16: output_enable(true); latch(false); break;
            case 17: latch(true); break;
            case 18: esp32_gpio_remove_board_bias(down); down = NULL; break;
            case 19: esp32_gpio_remove_board_bias(up); up = NULL; break;
            case 20: esp32_gpio_iomux_write(&controller, mux_addr, BIT(15), 4); break;
            case 21: gpio_write(0x4c, UINT32_MAX); gpio_write(0x58, UINT32_MAX); break;
            }
            observe_lines_and_pads();
        }
    }
    for (unsigned n = 0; n < GPIO_NPINS; n++) { esp32_gpio_unobserve_pad(observers[n]); }
    assert(!g_pad_observers && !g_board_biases && host_object_refs == 0);
    printf("GRID %s hash=%016" PRIx64 " events=%" PRIu64 " irq_count=%" PRIu64 " irq_hash=%016" PRIx64 "\n",
           s3 ? "s3" : "classic", observation_hash, observation_events, test_irq_count, test_irq_hash);
    return 0;
}
static int count_queries(bool s3, bool no_controller)
{
    host_s3 = s3;
    host_now_ns = 7331;
    esp32_gpio_init(OBJECT(&controller));
    if (s3) { esp32s3_gpio_pad_aux_init(&controller, &system_mem, 0x60008400); }
    if (no_controller) { g_gpio_device = NULL; }
    test_clock_calls = test_resolve_calls = 0;
    uint64_t hash = 0;
    for (unsigned n = 0; n < 100; n++) { hash ^= gpio_line64(); }
    printf("COUNT line clocks=%" PRIu64 " resolves=%" PRIu64 " hash=%" PRIu64 "\n", test_clock_calls, test_resolve_calls, hash);
    test_clock_calls = test_resolve_calls = 0;
    for (unsigned n = 0; n < 100; n++) { hash ^= esp32_gpio_get_line(35); }
    printf("COUNT pin clocks=%" PRIu64 " resolves=%" PRIu64 " hash=%" PRIu64 "\n", test_clock_calls, test_resolve_calls, hash);
    return 0;
}
int differential_main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "grid-s3")) { return differential_grid(true); }
    if (!strcmp(argv[1], "grid-classic")) { return differential_grid(false); }
    if (!strcmp(argv[1], "count-s3")) { return count_queries(true, false); }
    if (!strcmp(argv[1], "count-classic")) { return count_queries(false, false); }
    if (!strcmp(argv[1], "count-no-controller")) { return count_queries(true, true); }
    return fixture_main(argc, argv);
}

/* A clock that advances on every read catches batching independently from
 * fixed-clock equality. AW edges below use actual GPIO writes and observers. */
static unsigned batch_events;
static int64_t batch_before_ns, batch_commit_ns;
static uint64_t batch_prior_revision[2], batch_prior_sequence;
static unsigned callback_phase;
static void batch_observer(void *opaque, const Esp32GpioPadEvent *event)
{
    unsigned index = (uintptr_t)opaque;
    assert(event->after.pin == (index ? 21u : 2u));
    assert(event->before.at_ns == batch_before_ns);
    assert(event->after.at_ns == batch_commit_ns);
    assert(event->after.revision == batch_prior_revision[index] + 1);
    assert(event->commit_sequence == batch_prior_sequence + ++callback_phase);
    Esp32GpioPadSnapshot other;
    const int64_t fresh_sample = host_now_ns;
    assert(esp32_gpio_pad_snapshot(&controller, index ? 2 : 21, &other));
    assert(other.at_ns == fresh_sample);
    assert(other.at_ns > event->after.at_ns);
    assert(other.revision == batch_prior_revision[!index] + 1);
    batch_events++;
}
static int batch_clock_contract(void)
{
    host_now_ns = 1000000;
    init_controller();
    if (!TEST_BATCHED) {
        Esp32GpioPadSnapshot before[54];
        test_clock_calls = 0; test_clock_step_ns = 7;
        int64_t sampled = host_now_ns;
        esp32_gpio_capture_pads(&controller, before);
        assert(test_clock_calls == 54);
        for (unsigned n = 0; n < 54; n++) { assert(before[n].at_ns == sampled + 7 * n); }
        assert(before[0].at_ns != before[53].at_ns);
        printf("PASS negative-control per-pin timestamps differ, capture clocks=54\n");
        return 0;
    }
    for (unsigned index = 0; index < 2; index++) {
        pin = index ? 21 : 2;
        route(256); iomux(1, 1u << 9); output_enable(true); latch(false);
    }
    Esp32GpioPadObserver *observers[2];
    for (unsigned index = 0; index < 2; index++) {
        Error *err = NULL; Esp32GpioPadSnapshot initial;
        observers[index] = esp32_gpio_observe_pad(&controller, index ? 21 : 2,
                           batch_observer, (void *)(uintptr_t)index, &initial, &err);
        assert(observers[index] && !err);
    }
    Esp32GpioPadSnapshot before[54];
    test_clock_calls = 0; test_clock_step_ns = 7;
    int64_t before_sample = host_now_ns;
    esp32_gpio_capture_pads(&controller, before);
    assert(test_clock_calls == 1);
    for (unsigned n = 0; n < 54; n++) { assert(before[n].at_ns == before_sample); }
    int64_t previous_commit = -1;
    for (unsigned transaction = 0; transaction < 3; transaction++) {
        batch_prior_revision[0] = g_pad_revision[2];
        batch_prior_revision[1] = g_pad_revision[21];
        batch_prior_sequence = g_pad_sequence;
        callback_phase = 0;
        batch_before_ns = host_now_ns;
        batch_commit_ns = batch_before_ns + 7;
        assert(batch_before_ns > previous_commit);
        test_clock_calls = 0;
        gpio_write(transaction & 1 ? 0x0c : 0x08, (1u << 2) | (1u << 21));
        assert(test_clock_calls == 4); /* capture, notify, two fresh callback reads */
        assert(callback_phase == 2);
        assert(g_pad_sequence == batch_prior_sequence + 2);
        previous_commit = batch_commit_ns;
    }
    uint64_t revision2 = g_pad_revision[2], revision21 = g_pad_revision[21];
    uint64_t sequence = g_pad_sequence;
    test_clock_calls = 0;
    gpio_write(0x08, (1u << 2) | (1u << 21));
    assert(test_clock_calls == 2 && batch_events == 6); /* time alone makes no event */
    assert(g_pad_revision[2] == revision2 && g_pad_revision[21] == revision21);
    assert(g_pad_sequence == sequence);
    Esp32GpioPadSnapshot a, b;
    test_clock_calls = 0;
    assert(esp32_gpio_pad_snapshot(&controller, 2, &a));
    assert(esp32_gpio_pad_snapshot(&controller, 2, &b));
    assert(test_clock_calls == 2 && b.at_ns == a.at_ns + 7);
    assert(a.revision == b.revision);
    esp32_gpio_unobserve_pad(observers[0]); esp32_gpio_unobserve_pad(observers[1]);
    printf("PASS batched timestamps capture=1 notify=1 callbacks=6; all revisions committed before callbacks; independent point reads; no cache/clamp\n");
    return 0;
}
static void aw_write_edge_at(bool high, int64_t commit_at)
{
    assert(TEST_BATCHED);
    assert(commit_at - 7 >= host_now_ns);
    host_now_ns = commit_at - 7;
    test_clock_step_ns = 7;
    latch(high);
    test_clock_step_ns = 0;
    assert(aw->last_edge_ns == commit_at);
}
static void aw_ready_low(void)
{
    start(true, false);
    assert(aw->low_since_ns == 0);
    advance(500000);
    assert(!aw->ready && aw->reset_events == 0);
    uint64_t clocks = test_clock_calls;
    advance(500001);
    assert(test_clock_calls > clocks); /* unchanged timer reads actual current clock */
    assert(aw->ready && aw->qualified && aw->reset_events == 1);
}
static int aw_width_contract(int64_t duration, bool low)
{
    aw_ready_low();
    aw_write_edge_at(true, 600000);
    assert(aw->phase == AW3641_PROGRAMMING && aw->qualified);
    if (low) {
        aw_write_edge_at(false, 602000);
        assert(aw->qualified);
        aw_write_edge_at(true, 602000 + duration);
    } else {
        aw_write_edge_at(false, 600000 + duration);
    }
    const bool qualified = duration >= 750 && duration <= 10000;
    assert(aw->qualified == qualified);
    if (!qualified) {
        assert(aw->phase == AW3641_UNQUALIFIED);
        assert(!strcmp(aw->reason, "pulse-width-outside-recommended-window"));
    }
    printf("PASS AW %s duration=%" PRId64 " qualified=%d actual commit timestamps\n", low ? "low" : "high", duration, qualified);
    return 0;
}
static int aw_reset_contract(int64_t duration)
{
    start(true, false);
    assert(aw->low_since_ns == 0);
    /* Deliberately delay timer dispatch, as the actual model's edge path
     * must also recognize a complete observed long-low interval. */
    aw_write_edge_at(true, duration);
    const bool qualified = duration >= 500001;
    assert(aw->qualified == qualified);
    assert(aw->reset_events == (qualified ? 1u : 0u));
    assert(aw->phase == (qualified ? AW3641_PROGRAMMING : AW3641_UNQUALIFIED));
    printf("PASS AW late-reset duration=%" PRId64 " qualified=%d\n", duration, qualified);
    return 0;
}
static int aw_settle_contract(void)
{
    aw_ready_low();
    aw_write_edge_at(true, 600000);
    assert(aw->settle_at_ns == 1100000);
    advance(1099999); assert(!aw->active && aw->decoded_programs == 0);
    uint64_t clocks = test_clock_calls;
    advance(1100000); assert(aw->active && aw->decoded_programs == 1);
    assert(test_clock_calls > clocks);
    advance(1100001); assert(aw->active && aw->decoded_programs == 1);
    assert(aw->timeout_at_ns == 220600000);
    advance(220599999); assert(aw->active);
    clocks = test_clock_calls;
    advance(220600000); assert(!aw->active && aw->timeout_events == 1);
    assert(test_clock_calls > clocks);
    printf("PASS AW settle elapsed499999/500000/500001 and timeout exact; timer clock reads retained\n");
    return 0;
}
int advancing_main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "advancing-clock")) { return batch_clock_contract(); }
    if (!strncmp(argv[1], "aw-high-", 8)) { return aw_width_contract(atoll(argv[1]+8), false); }
    if (!strncmp(argv[1], "aw-low-", 7)) { return aw_width_contract(atoll(argv[1]+7), true); }
    if (!strncmp(argv[1], "aw-reset-", 9)) { return aw_reset_contract(atoll(argv[1]+9)); }
    if (!strcmp(argv[1], "aw-settle-timeout")) { return aw_settle_contract(); }
    return differential_main(argc, argv);
}

/* Additional host-only tests of actual stage3/stage4 C source. No guest values
 * or controller algorithms are substituted. All setup is fixture-owned. */
static void stage4_setup(bool s3)
{
    host_s3 = s3;
    host_now_ns = 1000000;
    test_clock_step_ns = 0;
    esp32_gpio_init(OBJECT(&controller));
    if (s3) { esp32s3_gpio_pad_aux_init(&controller, &system_mem, 0x60008400); }
}
static void stage4_clear_registers(void)
{
    assert(!g_pad_observers && !g_board_biases);
    memset(g_regs, 0, sizeof(g_regs));
    memset(g_od_origin, 0, sizeof(g_od_origin));
    g_open_drain = g_force_mask = g_force_level = g_external_seen = 0;
    g_ext_in = UINT64_MAX;
    gpio_iomux_reset();
    for (unsigned n = 0; n < (g_gpio_s3 ? 49u : 40u); n++) {
        g_regs[((g_gpio_s3 ? 0x554 : 0x530) + n * 4) / 4] = 256;
    }
}
static void stage4_gpio_matrix(unsigned n)
{
    if (n < 49) {
        /* FUN_IE deliberately disabled: raw pad IRQ is still high/low. */
        g_iomux_regs[n] = (g_gpio_s3 ? 1u : 2u) << 12;
        g_iomux_written[n] = g_iomux_pull_known[n] = true;
    }
}
static bool stage4_pending(unsigned n)
{
    return !!(g_regs[(n < 32 ? 0x44 : 0x50) / 4] & (1u << (n & 31)));
}
static void stage4_clear_status(unsigned n)
{
    uint64_t calls = test_irq_count;
    gpio_write(n < 32 ? 0x4c : 0x58, 1u << (n & 31));
    assert(test_irq_count == calls + 1);
}
static int stage4_irq_grid(bool s3)
{
    stage4_setup(s3);
    const unsigned limit = s3 ? 49 : 40;
    for (unsigned n = 0; n < limit; n++) {
        for (unsigned type = 0; type <= 7; type++) {
            for (unsigned en_case = 0; en_case < 3; en_case++) {
                unsigned enabled = en_case == 2 ? 31 : en_case;
                bool active = enabled != 0;
                stage4_clear_registers();
                pin = n;
                stage4_gpio_matrix(n);
                g_regs[(n < 32 ? 0x20 : 0x2c) / 4] = 1u << (n & 31);
                unsigned cfg_addr = (s3 ? 0x74 : 0x88) + n * 4;
                uint64_t calls = test_irq_count;
                gpio_write(cfg_addr, (type << 7) | (enabled << 13));
                assert(test_irq_count == calls + 1);
                assert(stage4_pending(n) == (active && type == 4));
                stage4_clear_status(n);
                assert(stage4_pending(n) == (active && type == 4));
                calls = test_irq_count;
                latch(true);
                assert(test_irq_count == calls + 1);
                assert(stage4_pending(n) == (active &&
                    (type == 1 || type == 3 || type == 4 || type == 5)));
                if (s3 && gpio_pad_valid(&controller, n)) {
                    assert(gpio_line64() & BIT(n));
                    assert(!(gpio_input64() & BIT(n)));
                }
                stage4_clear_status(n);
                assert(stage4_pending(n) == (active && type == 5));
                calls = test_irq_count;
                latch(false);
                assert(test_irq_count == calls + 1);
                assert(stage4_pending(n) == (active &&
                    (type == 2 || type == 3 || type == 4 || type == 5)));
                stage4_clear_status(n);
                assert(stage4_pending(n) == (active && type == 4));
                gpio_write(cfg_addr, type << 7); /* mask disables every type */
                stage4_clear_status(n);
                assert(!stage4_pending(n));
                calls = test_irq_count;
                uint64_t resolves = test_resolve_calls;
                gpio_update_irq();
                assert(test_irq_count == calls + 1);
                assert(test_resolve_calls >= resolves);
#if TEST_STAGE4B
                assert(test_resolve_calls == resolves); /* no enabled level IRQ */
#endif
                assert(!stage4_pending(n));
                /* Latched edge status still drives IRQ without line parsing. */
                g_regs[(n < 32 ? 0x44 : 0x50) / 4] |= 1u << (n & 31);
                calls = test_irq_count;
                resolves = test_resolve_calls;
                gpio_update_irq();
                assert(test_irq_count == calls + 1);
                assert(test_resolve_calls >= resolves);
#if TEST_STAGE4B
                assert(test_resolve_calls == resolves);
#endif
                assert(stage4_pending(n));
                observe_lines_and_pads();
            }
        }
    }
    printf("PASS irq-grid %s types0..7 enabled0/1/31 all-config-pins=%u hash=%016" PRIx64 "\n",
           s3 ? "s3" : "classic", limit, observation_hash);
    return 0;
}
static unsigned stage4_reentries;
static void stage4_reentrant_legacy(void *opaque, int n, int level)
{
    assert(n == 2 && level == 1 && !stage4_reentries);
    stage4_reentries++;
    esp32_gpio_set_input(3, 0);
    assert(stage4_pending(3));
    stage4_clear_status(3);
    assert(!stage4_pending(3));
}
static int stage4_reentrant(bool s3)
{
    stage4_setup(s3);
    stage4_clear_registers();
    stage4_gpio_matrix(2); stage4_gpio_matrix(3);
    g_regs[0x20 / 4] = BIT(2);
    g_regs[((s3 ? 0x74 : 0x88) + 3 * 4) / 4] = (2u << 7) | BIT(13);
    /* Prove the old high level through the actual input API, so a wrongly
     * reused captured image remains known-high rather than falling back to
     * the current legacy bit after our synchronous callback changed it. */
    esp32_gpio_set_input(3, 1);
    Esp32GpioPadSnapshot initial;
    assert(esp32_gpio_pad_snapshot(&controller, 3, &initial));
    assert(initial.known && initial.level);
    esp32_gpio_add_out_listener(2, stage4_reentrant_legacy, NULL);
    uint64_t calls = test_irq_count;
    pin = 2; latch(true);
    assert(stage4_reentries == 1 && !(gpio_line64() & BIT(3)));
    /* Nested input, nested status clear, then outer fresh-after transition. */
    assert(test_irq_count == calls + 3);
    assert(stage4_pending(3));
    observe_lines_and_pads();
    printf("PASS legacy-reentry %s fresh-after hash=%016" PRIx64 "\n",
           s3 ? "s3" : "classic", observation_hash);
    return 0;
}
static int stage4_captured_line(bool s3)
{
    stage4_setup(s3);
    stage4_clear_registers();
    for (unsigned step = 0; step < 10; step++) {
        for (unsigned n = 0; n < GPIO_NPINS; n++) {
            stage4_gpio_matrix(n);
            g_regs[((s3 ? 0x554 : 0x530) + n * 4) / 4] =
                step & 1 ? 73 : 256 | (step & 2 ? BIT(9) : 0);
        }
        g_ext_in = UINT64_C(0x5555555555555555) ^ ((uint64_t)step << 16);
        g_regs[0x04 / 4] = 0x98765432u ^ step;
        g_regs[0x10 / 4] = 0xa55au;
        g_regs[0x20 / 4] = 0x87654321u;
        g_regs[0x2c / 4] = 0x5aa5u;
        g_open_drain = step & 4 ? UINT64_C(0x5a5aa5a5) : 0;
        g_force_mask = step & 8 ? UINT64_C(0x777) : 0;
        g_force_level = UINT64_C(0x555);
        Esp32GpioPadSnapshot captured[54];
        esp32_gpio_capture_pads(&controller, captured);
        uint64_t line = gpio_line64();
#if TEST_STAGE4A
        assert(gpio_line64_captured(&controller, captured) == line);
        Esp32GpioState wrong = { 0 };
        esp32_gpio_capture_pads(&wrong, captured);
        assert(gpio_line64_captured(&wrong, captured) == line);
#endif
        observe_lines_and_pads();
        assert(esp32_gpio_get_line(-1) == 1 && esp32_gpio_get_line(54) == 1);
        uint64_t clocks = test_clock_calls, calls = test_irq_count;
        esp32_gpio_set_input(-1, 0); esp32_gpio_set_input(54, 0);
        assert(test_clock_calls == clocks && test_irq_count == calls);
    }
    g_gpio_device = NULL;
    Esp32GpioPadSnapshot captured[54];
    esp32_gpio_capture_pads(NULL, captured);
#if TEST_STAGE4A
    assert(gpio_line64_captured(NULL, captured) == gpio_line64());
#endif
    uint64_t calls = test_irq_count;
    gpio_update_irq(); gpio_transition_irq(0, UINT64_MAX);
    assert(test_irq_count == calls);
    printf("PASS captured-line %s unknown/classic/holes/null/invalid hash=%016" PRIx64 "\n",
           s3 ? "s3" : "classic", observation_hash);
    return 0;
}
static int stage4_transaction_counts(void)
{
    stage4_setup(true); stage4_clear_registers(); stage4_gpio_matrix(2);
    g_regs[0x20 / 4] = BIT(2);
    test_resolve_calls = test_clock_calls = test_irq_count = 0;
    test_irq_hash = UINT64_C(1469598103934665603);
    for (unsigned n = 0; n < 100; n++) {
        gpio_write(n & 1 ? 0x0c : 0x08, BIT(2));
    }
    assert(test_clock_calls == (TEST_CANDIDATE ? 200u : 27900u) && test_irq_count == 100);
    printf("WORK transaction resolves=%" PRIu64 " clocks=%" PRIu64 " irq_count=%" PRIu64 "\n",
           test_resolve_calls, test_clock_calls, test_irq_count);
    printf("PASS transaction-counts line=%016" PRIx64 " sequence=%" PRIu64 " revision2=%" PRIu64 " irq_hash=%016" PRIx64 "\n",
           gpio_line64(), g_pad_sequence, g_pad_revision[2], test_irq_hash);
    return 0;
}
int stage4_main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "irq-grid-s3")) { return stage4_irq_grid(true); }
    if (!strcmp(argv[1], "irq-grid-classic")) { return stage4_irq_grid(false); }
    if (!strcmp(argv[1], "legacy-reentry-s3")) { return stage4_reentrant(true); }
    if (!strcmp(argv[1], "legacy-reentry-classic")) { return stage4_reentrant(false); }
    if (!strcmp(argv[1], "captured-line-s3")) { return stage4_captured_line(true); }
    if (!strcmp(argv[1], "captured-line-classic")) { return stage4_captured_line(false); }
    if (!strcmp(argv[1], "transaction-counts")) { return stage4_transaction_counts(); }
    return advancing_main(argc, argv);
}

static unsigned bank_events, bank_legacy_events;
static bool bank_record;
static bool bank_clear_callback_status;
static Esp32GpioPadObserver *bank_dynamic_observer;
static void bank_pad(void *opaque, const Esp32GpioPadEvent *event)
{
    if (!bank_record) { return; }
    observe_bytes(&event->cause, sizeof(event->cause));
    observe_bytes(&event->change_mask, sizeof(event->change_mask));
    observe_bytes(&event->commit_sequence, sizeof(event->commit_sequence));
    observe_bytes(&event->before, sizeof(event->before));
    observe_bytes(&event->after, sizeof(event->after));
    Esp32GpioPadSnapshot other;
    unsigned query = event->after.pin == 2 ? 21 : 2;
    assert(esp32_gpio_pad_snapshot(&controller, query, &other));
    assert(other.revision == g_pad_revision[query]);
    observe_bytes(&other, sizeof(other));
    bank_events++;
}
static void bank_state(void)
{
    observe_bytes(g_regs, sizeof(g_regs));
    observe_bytes(g_pad_revision, sizeof(g_pad_revision));
    observe_bytes(&g_pad_sequence, sizeof(g_pad_sequence));
    uint64_t line = gpio_line64(); observe_bytes(&line, sizeof(line));
    for (int n = -1; n <= GPIO_NPINS; n++) {
        int level = esp32_gpio_get_line(n);
        assert(level == (n < 0 || n >= GPIO_NPINS ? 1 : !!(line & BIT(n))));
        observe_bytes(&level, sizeof(level));
    }
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        Esp32GpioPadSnapshot s;
        bool valid = esp32_gpio_pad_snapshot(&controller, n, &s);
        observe_bytes(&valid, sizeof(valid));
        if (valid) { observe_bytes(&s, sizeof(s)); }
    }
}
static void bank_init(bool s3, bool all_observers)
{
    host_s3 = s3;
    esp32_gpio_init(OBJECT(&controller));
    if (s3) { esp32s3_gpio_pad_aux_init(&controller, &system_mem, 0x60008400); }
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        if (!gpio_pad_valid(&controller, n)) { continue; }
        pin = n; route(256);
        esp32_gpio_iomux_write(&controller,
            s3 ? 4 + n * 4 : classic_iomux_offset[n],
            ((s3 ? 1u : 2u) << 12) | BIT(9), 4);
        output_enable(true); latch(false);
        if (all_observers) {
            Error *err = NULL; Esp32GpioPadSnapshot initial;
            assert(esp32_gpio_observe_pad(&controller, n, bank_pad, NULL, &initial, &err));
            assert(!err);
        }
    }
}
static void bank_print(const char *name)
{
    printf("BANK %s hash=%016" PRIx64 " events=%u legacy=%u irq_count=%" PRIu64 " irq_hash=%016" PRIx64 "\n",
        name, observation_hash, bank_events, bank_legacy_events, test_irq_count, test_irq_hash);
}
static int bank_grid(bool s3, bool advancing)
{
    bank_init(s3, true);
    static unsigned bias_owners[2];
    for (unsigned n = 0; n < GPIO_NPINS; n++) {
        if (!gpio_pad_valid(&controller, n)) { continue; }
        pin = n;
        switch (n % 6) {
        case 0: break;
        case 1: esp32_gpio_iomux_write(&controller, s3 ? 4 + n * 4 : classic_iomux_offset[n], 7u << 12, 4); break;
        case 2: esp32_gpio_set_open_drain(n, true); break;
        case 3: esp32_gpio_force_line(n, n & 1); break;
        case 4: esp32_gpio_set_input(n, 1); break;
        case 5: {
            Error *err = NULL;
            assert(esp32_gpio_add_board_bias(&controller, n, ESP32_GPIO_BIAS_PULL_UP, &bias_owners[0], &err));
            assert(!err);
            assert(esp32_gpio_add_board_bias(&controller, n, ESP32_GPIO_BIAS_PULL_DOWN, &bias_owners[1], &err));
            assert(!err); break;
        }
        }
    }
    bank_record = true; test_clock_step_ns = advancing ? 7 : 0;
    const unsigned addresses[] = { 0x04,0x08,0x0c,0x10,0x14,0x18,0x20,0x24,0x28,0x2c,0x30,0x34 };
    for (unsigned a = 0; a < G_N_ELEMENTS(addresses); a++) {
        for (unsigned bit = 0; bit < 32; bit++) {
            uint64_t value = (UINT64_C(0xa5a5) << 32) | (1u << bit);
            esp32_gpio_write(&controller, addresses[a], value, 4);
            bank_state();
        }
        esp32_gpio_write(&controller, addresses[a], 0, 4); bank_state();
        esp32_gpio_write(&controller, addresses[a], UINT64_MAX, 4); bank_state();
    }
    bank_print(advancing ? "grid-advancing" : s3 ? "grid-s3" : "grid-classic");
    return 0;
}
static void bank_legacy(void *opaque, int n, int level)
{
    bank_legacy_events++;
    esp32_gpio_set_input(35, level);
    if (bank_clear_callback_status) { gpio_write(0x58, BIT(3)); }
}
static void bank_register_legacy(void *opaque, const Esp32GpioPadEvent *event)
{
    bool *registered = opaque;
    if (!*registered && (event->change_mask & ESP32_GPIO_PAD_CHANGE_LEVEL)) {
        esp32_gpio_add_out_listener(2, bank_legacy, NULL);
        *registered = true;
    }
}
static int bank_fallback(const char *kind)
{
    bank_init(true, true); pin = 2; bank_record = true; test_clock_step_ns = 7;
    unsigned size = 4, target_pin = 2; bool expected_fast = false;
    static bool registered;
    if (!strcmp(kind, "selected-listener")) {
        esp32_gpio_add_out_listener(2, bank_legacy, NULL);
    } else if (!strcmp(kind, "selected-hole") || !strcmp(kind, "selected-high")) {
        target_pin = !strcmp(kind, "selected-hole") ? 23 : 50;
        gpio_write(target_pin < 32 ? 0x24 : 0x30, 1u << (target_pin & 31));
        esp32_gpio_add_out_listener(target_pin, bank_legacy, NULL);
    } else if (!strcmp(kind, "unselected-listener")) {
        esp32_gpio_add_out_listener(40, bank_legacy, NULL); expected_fast = true;
    } else if (!strcmp(kind, "dynamic-listener") || !strcmp(kind, "dynamic-irq")) {
        if (!strcmp(kind, "dynamic-irq")) {
            pin = 35; output_enable(false);
            esp32_gpio_set_input(35, 0);
            gpio_write(0x74 + 35 * 4, (1u << 7) | BIT(13));
            Esp32GpioPadSnapshot input;
            assert(esp32_gpio_pad_snapshot(&controller, 35, &input));
            assert(input.known && !input.level);
            bank_clear_callback_status = true;
            pin = 2;
        }
        Error *err = NULL; Esp32GpioPadSnapshot initial;
        bank_dynamic_observer = esp32_gpio_observe_pad(&controller, 2, bank_register_legacy, &registered, &initial, &err);
        assert(bank_dynamic_observer && !err); expected_fast = true;
    } else if (!strcmp(kind, "level-hole")) {
        gpio_write(0x74 + 23 * 4, (4u << 7) | BIT(13));
    } else if (!strcmp(kind, "level-other")) {
        gpio_write(0x74 + 35 * 4, (5u << 7) | BIT(13));
    } else if (!strncmp(kind, "size-", 5)) {
        size = atoi(kind + 5);
    } else if (!strcmp(kind, "pending-disabled")) {
        gpio_write(0x74 + 2 * 4, (3u << 7) | BIT(13));
        latch(true); latch(false);
        assert(g_regs[0x44 / 4] & BIT(2));
        gpio_write(0x74 + 2 * 4, 0);
        expected_fast = true;
    } else if (!strncmp(kind, "hole-edge-", 10) || !strncmp(kind, "edge-", 5)) {
        bool hole = !strncmp(kind, "hole-edge-", 10);
        unsigned type = atoi(kind + (hole ? 10 : 5));
        assert(type >= 1 && type <= 3);
        target_pin = hole ? 23 : 2;
        if (hole) { gpio_write(0x24, BIT(23)); }
        gpio_write(0x74 + target_pin * 4, (type << 7) | BIT(13)); expected_fast = true;
    } else { abort(); }
    test_fast_calls = 0;
    esp32_gpio_write(&controller, target_pin < 32 ? 0x08 : 0x14,
                     1u << (target_pin & 31), size);
    if (TEST_CANDIDATE) { assert(test_fast_calls == (expected_fast ? 1u : 0u)); }
    bank_state();
    if (!strcmp(kind, "selected-listener") || !strcmp(kind, "dynamic-listener") ||
        !strcmp(kind, "dynamic-irq") ||
        !strcmp(kind, "selected-hole") || !strcmp(kind, "selected-high")) {
        assert(bank_legacy_events == 1);
        assert((g_ext_in & BIT(35)) != 0);
    }
    if (!strcmp(kind, "dynamic-irq")) { assert(g_regs[0x50 / 4] & BIT(3)); }
    if (!strcmp(kind, "pending-disabled")) { assert(test_irq_last == 1); }
    bank_print(kind); return 0;
}
static int bank_work_count(void)
{
    bank_init(true, false); pin = 2;
    test_fast_calls = test_clock_calls = test_resolve_calls = 0;
    puts("BEGIN BANK COUNT");
    for (unsigned n = 0; n < 100; n++) { latch(!(n & 1)); }
    assert(test_clock_calls == (TEST_CANDIDATE ? 200u : 27900u));
    assert(test_resolve_calls == (TEST_CANDIDATE ? 200u : 27900u));
    assert(test_fast_calls == (TEST_CANDIDATE ? 100u : 0u));
    printf("COUNT bank clocks=%" PRIu64 " resolves=%" PRIu64 " fast=%" PRIu64 "\n", test_clock_calls, test_resolve_calls, test_fast_calls);
    return 0;
}
static int bank_guard_contract(void)
{
#if TEST_CANDIDATE
    bank_init(true, false);
    Esp32GpioPadSnapshot before[54];
    Esp32GpioState foreign = { 0 };
    uint64_t clocks = test_clock_calls, resolves = test_resolve_calls;
    uint32_t old = g_regs[0x04 / 4];
    assert(!gpio_try_bank_fast(NULL, 0x08, BIT(2), 4, before));
    assert(!gpio_try_bank_fast(&foreign, 0x08, BIT(2), 4, before));
    g_gpio_device = NULL; /* finalize leaves its previous layout flag */
    assert(g_gpio_s3);
    assert(!gpio_try_bank_fast(NULL, 0x08, BIT(2), 4, before));
    g_gpio_device = &controller; g_gpio_s3 = false;
    assert(!gpio_try_bank_fast(&controller, 0x08, BIT(2), 4, before));
    g_gpio_s3 = true;
    assert(!gpio_try_bank_fast(&controller, 0x08, BIT(2), 2, before));
    assert(!gpio_try_bank_fast(&controller, 0x74, BIT(2), 4, before));
    assert(test_clock_calls == clocks && test_resolve_calls == resolves);
    assert(g_regs[0x04 / 4] == old);
#endif
    printf("PASS bank guard rejects null/foreign/finalized/classic/width/address without writes or sampling\n");
    return 0;
}
static unsigned reset_legacy_calls;
static void reset_level_prepare(void *opaque, int n, int level)
{
    pin = 3;
    iomux(1, BIT(9));
    esp32_gpio_set_input(3, 1);
    gpio_write(0x74 + 3 * 4, (5u << 7) | BIT(13));
    assert(stage4_pending(3));
    pin = 2;
}
static void reset_level_legacy(void *opaque, int n, int level)
{
    assert(n == 2 && level == 1 && !reset_legacy_calls);
    reset_legacy_calls++;
    esp32_gpio_set_input(3, 0);
    stage4_clear_status(3);
    assert(!stage4_pending(3));
}
static int reset_level_contract(void)
{
    stage4_setup(true); stage4_clear_registers();
    stage4_gpio_matrix(2); stage4_gpio_matrix(3);
    g_regs[0x20 / 4] = BIT(2);
    esp32_gpio_set_input(3, 1);
    esp32_gpio_add_reset_listener(2, reset_level_prepare, NULL);
    esp32_gpio_add_out_listener(2, reset_level_legacy, NULL);
    test_irq_count = 0;
    test_irq_hash = UINT64_C(1469598103934665603);
    puts("BEGIN RESET LEVEL");
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert(reset_legacy_calls == 1);
    assert(!(gpio_line64() & BIT(3)));
    printf("RESET pending=%d irq_calls=%" PRIu64 " last_irq=%d status0=%08x status1=%08x\n",
        stage4_pending(3), test_irq_count, test_irq_last,
        g_regs[0x44 / 4], g_regs[0x50 / 4]);
    fflush(stdout);
    assert(!stage4_pending(3));
    puts("PASS reset-level current line after legacy callback");
    return 0;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    test_normalize_timestamp = !strncmp(argv[1], "bank-", 5);
    if (!strcmp(argv[1], "bank-grid-s3")) { return bank_grid(true, false); }
    if (!strcmp(argv[1], "bank-grid-classic")) { return bank_grid(false, false); }
    if (!strcmp(argv[1], "bank-grid-advancing")) { return bank_grid(true, true); }
    if (!strcmp(argv[1], "bank-work-count")) { return bank_work_count(); }
    if (!strcmp(argv[1], "bank-guards")) { return bank_guard_contract(); }
    if (!strcmp(argv[1], "reset-level")) { return reset_level_contract(); }
    if (!strncmp(argv[1], "bank-", 5)) { return bank_fallback(argv[1] + 5); }
    return stage4_main(argc, argv);
}
