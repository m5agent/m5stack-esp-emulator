"""Native observer removal must preserve exact object subscription membership.

The preimage is inspected by event counts and repaired before object deletion;
cleanup never changes an already recorded failure into a passing observation.
"""
import json
import lvgl as lv


def emit(target, method, ok, domain, **details):
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl." + target, method=method,
          status="STATE_PASS" if ok else "FAIL", argument_domain=domain, **details)))


def observer(subject, obj, calls):
    return subject.add_observer_obj(lambda o, s: calls.append(s.get_int()), obj, None)


def explicit_removal(screen):
    obj, one, two = lv.obj(screen), lv.subject_t(), lv.subject_t()
    one.init_int(1)
    two.init_int(2)
    base = obj.get_event_count()
    calls, deleted = [], []
    a = observer(one, obj, calls)
    observer(two, obj, calls)
    obj.add_event_cb(lambda e: deleted.append(e.get_code()), lv.EVENT.DELETE, None)
    before = obj.get_event_count()
    a.remove()
    after = obj.get_event_count()
    emit("observer_t", "remove", before == base + 3 and after == before - 1,
         "object-owned observer explicit removal detaches only its exact automatic subscription",
         before=before, after=after, base=base)
    if after != before - 1:
        # The original observer's event descriptor is at its recorded index.
        obj.remove_event(base)
        print("OBSERVER_CLEANUP_REPAIR stale explicit-removal subscription")
    obj.remove_from_subject(two)
    one.deinit()
    two.deinit()
    obj.delete()
    emit("observer_t", "remove", deleted == [lv.EVENT.DELETE],
         "unrelated delete callback survives observer cleanup", callbacks=deleted)


def shared_subjects(screen):
    obj, one, two = lv.obj(screen), lv.subject_t(), lv.subject_t()
    one.init_int(10)
    two.init_int(20)
    calls = []
    base = obj.get_event_count()
    observer(one, obj, calls)
    observer(two, obj, calls)
    first_descriptor = obj.get_event_dsc(base)
    before = obj.get_event_count()
    two.deinit()
    after = obj.get_event_count()
    # Generated struct equality compares descriptor addresses, without reading
    # the removed descriptor's storage. Count alone cannot identify membership.
    retained_first = obj.get_event_dsc(base) == first_descriptor
    emit("subject_t", "deinit", after == before - 1 and retained_first,
         "tearing down the later subject preserves the earlier subject subscription",
         before=before, after=after, retained_first=retained_first)
    if not retained_first:
        obj.remove_event(base)
        print("OBSERVER_CLEANUP_REPAIR stale shared-object subscription")
    calls[:] = []
    one.set_int(11)
    emit("subject_t", "notify", calls == [11], "unrelated live subject still delivers its changed value", calls=calls)
    one.deinit()
    obj.delete()


def automatic_delete(screen):
    obj, subject = lv.obj(screen), lv.subject_t()
    subject.init_int(30)
    calls = []
    observer(subject, obj, calls)
    calls[:] = []
    before = screen.get_child_count()
    obj.delete()
    subject.set_int(31)
    emit("obj", "delete", screen.get_child_count() == before - 1 and not calls,
         "object deletion automatically detaches its observer before another subject update", calls=calls)
    subject.deinit()


try:
    lv.init()
    display = lv.display_create(32, 24)
    screen = display.get_screen_active()
    for fn in (explicit_removal, shared_subjects, automatic_delete):
        try:
            fn(screen)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.observer_cleanup", method=fn.__name__, status="FIXTURE_ERROR", error=repr(error))))
    display.delete()
except Exception as error:
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.observer_cleanup", method="run", status="FIXTURE_ERROR", error=repr(error))))
print("LVGL_OBSERVER_CLEANUP_DONE")
