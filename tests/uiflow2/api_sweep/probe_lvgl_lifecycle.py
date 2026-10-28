"""Cold LVGL subsystem lifecycle calls, with configuration limits explicit."""
import json


def emit(target, method, status, **details):
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl" + ("." + target if target else ""), method=method, status=status, **details)))


def check(target, method, action, oracle, reason):
    try:
        value = action()
        emit(target, method, "STATE_PASS" if oracle(value) else "FAIL", oracle=reason,
             value=value if isinstance(value, (int, bool, str, tuple, list)) or value is None else repr(value))
        return value
    except Exception as error:
        emit(target, method, "FAIL", oracle=reason, error=repr(error))


def memory(lv):
    for name in ("mem_init", "mem_deinit"):
        getattr(lv, name)()
        emit("", name, "CALL_OK", oracle="LV_STDLIB_MICROPYTHON has no allocator lifecycle state; actual no-op called")
    pool_bytes = bytearray(64)
    pool = lv.mem_add_pool(pool_bytes, len(pool_bytes))
    emit("", "mem_add_pool", "BLOCKED_MODEL", value=repr(pool), oracle="LV_STDLIB_MICROPYTHON returns NULL; native memory pools unsupported")
    lv.mem_remove_pool(pool)
    emit("", "mem_remove_pool", "BLOCKED_MODEL", oracle="LV_STDLIB_MICROPYTHON removal is a no-op; memory pools unsupported")
    for method, alloc in (("free", lv.malloc), ("free_core", lv.malloc_core)):
        owned = alloc(8)
        owned.__dereference__(8)[:] = b"OWNEDBUF"
        getattr(lv, method)(owned)
        emit("", method, "CALL_OK", oracle="owned allocation freed once; independent allocator accounting unsupported")


def animation(lv):
    anim = lv.anim_t()
    anim.init()
    anim.set_duration(100)
    anim.set_reverse_duration(50)
    anim.set_reverse_delay(20)
    anim.set_repeat_delay(10)
    anim.set_repeat_count(2)
    check("anim_t", "get_playtime", anim.get_playtime, lambda v: v == 360, "two repeats include forward/reverse duration and both delays")
    anim.set_user_data({"nonce": "GET"})
    gotten = []
    def get_value(a):
        gotten.append(a.get_user_data().__cast__()["nonce"])
        return 7
    def execute(a, value):
        pass
    try:
        anim.set_get_value_cb(get_value)
        anim.set_custom_exec_cb(execute)
        anim.set_values(0, 10)
        running = anim.start()
        check("anim_t", "set_get_value_cb", lambda: list(gotten), lambda v: v == ["GET"], "starting actual animation invokes configured native getter")
        check("anim_t", "custom_get", lambda: running.custom_get(execute) is not None, bool, "custom callback and variable resolve running native animation")
        check("anim_t", "custom_delete", lambda: (running.custom_delete(execute), running.custom_get(execute) is None), lambda v: v == (True, True), "custom callback deletion removes actual running animation")
    except Exception as error:
        emit("anim_t", "set_get_value_cb", "FAIL", error=repr(error), oracle="valid getter/custom callback recipe")
    lv.anim_delete_all()
    timeline = lv.anim_timeline_create()
    check("", "anim_timeline_create", timeline.get_progress, lambda v: v == 65535, "new stopped animation timeline is initialized at its completed endpoint")
    timeline.delete()
    check("", "anim_refr_now", lambda: (lv.anim_refr_now(), lv.anim_count_running())[1], lambda v: v == 0, "explicit animation refresh leaves empty animation registry")
    target = bytearray(b"TARGET")
    event = lv.event_t({"original_target": target})
    event.push()
    lv.timer_handler_set_resume_cb(lv.event_mark_deleted, target)
    timer = lv.timer_create_basic()
    lv.timer_handler_set_resume_cb(None, None)
    check("", "timer_handler_set_resume_cb", lambda: event.deleted, bool, "native callback with exact void-pointer ABI marks retained active event deleted")
    check("", "event_mark_deleted", lambda: event.deleted, bool, "actual native resume callback matches retained target pointer and marks active event deleted")
    event.pop()
    timer.delete()


def subsystems(lv):
    for subsystem in ("group", "fs", "layout", "refr"):
        getattr(lv, subsystem + "_deinit")()
        emit("", subsystem + "_deinit", "CALL_OK", oracle="empty owned subsystem torn down before matching reinitialization")
        getattr(lv, subsystem + "_init")()
        if subsystem == "group":
            check("", "group_init", lv.group_get_count, lambda v: v == 0, "reinitialized group registry is empty")
        elif subsystem == "fs":
            check("", "fs_init", lambda: lv.fs_get_letters(bytearray(32)), lambda v: v == "", "reinitialized filesystem registry has no drivers")
        else:
            emit("", subsystem + "_init", "CALL_OK", oracle="subsystem reinitialized; later logical render/layout fixture supplies separate behavior evidence")
    for name in ("span_stack_deinit", "span_stack_init"):
        getattr(lv, name)()
        emit("", name, "CALL_OK", oracle="native span temporary-stack lifecycle called; allocator accounting unsupported")
    for subsystem in ("anim", "timer"):
        getattr(lv, subsystem + "_core_deinit")()
        emit("", subsystem + "_core_deinit", "CALL_OK", oracle="empty owned scheduler core deinitialized")
        getattr(lv, subsystem + "_core_init")()
        if subsystem == "anim":
            check("", "anim_core_init", lv.anim_count_running, lambda v: v == 0, "fresh animation core starts empty")
        else:
            timer = lv.timer_create(lambda t: None, 10, None)
            check("", "timer_core_init", lambda: timer.period, lambda v: v == 10, "reinitialized timer core creates actual timer with exact period")
            timer.delete()
    for name in ("os_init", "os_get_idle_percent"):
        value = getattr(lv, name)()
        emit("", name, "BLOCKED_MODEL", value=value, oracle="LV_OS_NONE has no OS task/idle-accounting implementation")


def run():
    import lvgl as lv
    lv.init()
    for stage in (memory, animation, subsystems):
        try:
            stage(lv)
        except Exception as error:
            emit("lifecycle", stage.__name__, "FIXTURE_ERROR", error=repr(error))
    lv.deinit()
    lv.mp_lv_deinit_gc()
    emit("", "mp_lv_deinit_gc", "CALL_OK", oracle="binding root teardown invoked after native LVGL deinit; no exposed root accounting oracle")
    lv.mp_lv_init_gc()
    lv.init()
    check("", "mp_lv_init_gc", lv.is_initialized, bool, "binding root reinitialization supports complete native LVGL initialization")


try:
    run()
except Exception as error:
    emit("lifecycle", "run", "FIXTURE_ERROR", error=repr(error))
print("LVGL_LIFECYCLE_DONE")
