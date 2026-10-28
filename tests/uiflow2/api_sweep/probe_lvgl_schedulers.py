"""Native scheduler/global APIs with a controlled tick and real callbacks."""
import json


def check(target, method, action, oracle, reason):
    try:
        value = action()
        passed = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""), "method": method,
            "status": "STATE_PASS" if passed else "FAIL", "oracle": reason,
            "value": value if isinstance(value, (bool, int, str, tuple, list)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""), "method": method,
            "status": "FAIL", "oracle": reason, "error": repr(error)}))


def timers(lv):
    hits = []
    timer = lv.timer_create(lambda item: hits.append(item.get_user_data().__cast__()["nonce"]), 5, {"nonce": "TIMER"})
    lv.tick_inc(6)
    lv.timer_handler()
    check("", "timer_create", lambda: list(hits), lambda x: x == ["TIMER"], "created native timer invokes actual callback with owned data")
    for method in ("timer_handler", "task_handler", "timer_handler_run_in_period", "timer_periodic_handler"):
        before = len(hits)
        lv.tick_inc(6)
        args = (5,) if method == "timer_handler_run_in_period" else ()
        check("", method, lambda method=method, args=args: (getattr(lv, method)(*args), len(hits) - before)[1], lambda x: x == 1, "handler dispatches one due native timer callback")
    lv.timer_enable(False)
    before = len(hits)
    lv.tick_inc(6)
    lv.timer_handler()
    check("", "timer_enable", lambda: len(hits), lambda x: x == before, "global disabled scheduler suppresses due callback")
    lv.timer_enable(True)
    lv.timer_handler()
    check("", "timer_enable.resume", lambda: len(hits), lambda x: x == before + 1, "global scheduler resumes due callbacks")
    check("", "timer_get_idle", lv.timer_get_idle, lambda x: 0 <= x <= 100, "native scheduler idle value remains in percent range")
    check("", "timer_get_time_until_next", lv.timer_get_time_until_next, lambda x: 0 <= x <= 5, "next due time bounded by known five millisecond timer")
    basic = lv.timer_create_basic()
    check("", "timer_create_basic", basic.get_paused, lambda x: not x, "basic native timer is initially active")
    basic.delete()
    timer.delete()
    pending = []
    data = {"nonce": "ASYNC"}
    callback = lambda context: pending.append(context.__cast__()["nonce"])
    result = lv.async_call(callback, data)
    lv.timer_handler()
    check("", "async_call", lambda: (result, list(pending)), lambda x: x == (lv.RESULT.OK, ["ASYNC"]), "native deferred callback actually runs once")
    pending[:] = []
    lv.async_call(callback, data)
    code = lv.async_call_cancel(callback, data)
    lv.timer_handler()
    check("", "async_call_cancel", lambda: (code, list(pending)), lambda x: x == (lv.RESULT.OK, []), "exact deferred callback identity is cancelled before dispatch")


def native_animation(lv):
    storage = bytearray(b"DATAKEEP")
    animation = lv.anim_t()
    animation.init()
    animation.set_var(storage)
    animation.set_exec_cb(lv.memzero)
    animation.set_values(0, 4)
    animation.set_duration(40)
    animation.set_repeat_count(0)
    running = animation.start()
    check("anim_t", "set_var", lambda: bytes(storage).decode(), lambda x: x == "DATAKEEP", "native callback receives the actual assigned object variable")
    for _ in range(5):
        lv.tick_inc(10)
        lv.timer_handler()
    check("anim_t", "set_exec_cb", lambda: bytes(storage).hex(), lambda x: x == (bytes(4) + b"KEEP").hex(), "native lv_memzero callback clears four requested bytes and preserves adjacent guard bytes")
    animation.set_delay(100)
    animation.start()
    found = lv.anim_get(storage, lv.memzero)
    check("", "anim_get", lambda: found.get_delay(), lambda x: x == 100, "native animation lookup resolves exact object and callback")
    check("", "anim_delete", lambda: (lv.anim_delete(storage, lv.memzero), lv.anim_get(storage, lv.memzero)), lambda x: x == (True, None), "exact native animation deletion removes lookup")
    animation.start()
    lv.anim_delete_all()
    check("", "anim_delete_all", lv.anim_count_running, lambda x: x == 0, "all owned native animations removed")
    check("", "anim_get_timer", lambda: lv.anim_get_timer() is not None, bool, "animation engine retains its scheduling timer after owned animations complete")
    for name in ("anim_speed", "anim_speed_clamped"):
        args = (100,) if name == "anim_speed" else (100, 100, 2000)
        encoded = getattr(lv, name)(*args)
        check("", name, lambda: lv.anim_resolve_speed(encoded, 0, 100), lambda x: x == 1000, "100px per second across 100px resolves to one second")
    check("", "anim_resolve_speed", lambda: lv.anim_resolve_speed(lv.anim_speed(100), 0, 100), lambda x: x == 1000, "encoded animation speed decoded against known distance")
    check("", "anim_speed_to_time", lambda: lv.anim_speed_to_time(100, 0, 100), lambda x: x == 1000, "direct known distance/speed conversion")



def os_configuration(lv):
    # The pinned official lv_conf.h selects LV_OS_NONE. Observe exported
    # returns but do not mistake inline no-ops for threading/mutex support.
    storage = bytearray(32)
    methods = [("thread_init", (storage, "owned-test", 0, None, 1024, None), lv.RESULT.INVALID),
               ("thread_delete", (storage,), lv.RESULT.INVALID)]
    methods += [("mutex_" + suffix, (storage,), lv.RESULT.OK) for suffix in ("init", "lock", "lock_isr", "unlock", "delete")]
    methods += [("thread_sync_" + suffix, (storage,), lv.RESULT.INVALID) for suffix in ("init", "wait", "signal", "signal_isr", "delete")]
    methods += [("lock", (), None), ("lock_isr", (), lv.RESULT.OK), ("unlock", (), None)]
    for name, arguments, expected in methods:
        try:
            value = getattr(lv, name)(*arguments)
            status = "BLOCKED_MODEL" if value == expected else "FAIL"
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name, "status": status,
                "value": value, "blocker_scope": "firmware-configuration",
                "oracle": "official LV_OS_NONE inline implementation has no real thread, mutex or synchronization data plane"}))
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name, "status": "FAIL", "error": repr(error), "oracle": "LV_OS_NONE exported signature invocation"}))


def run():
    import lvgl as lv
    lv.init()
    for name, action in (("timers", timers), ("native_animation", native_animation), ("os_configuration", os_configuration)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name + "_fixture", "status": "NOT_RUN", "oracle": repr(error)}))
    lv.deinit()


try:
    run()
except Exception as error:
    print("LVGL_SCHEDULERS_ERROR", repr(error))
print("LVGL_SCHEDULERS_DONE")
