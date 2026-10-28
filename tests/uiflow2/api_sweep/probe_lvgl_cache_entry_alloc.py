"""Raw native cache-entry allocation; never repair metadata before its oracle."""
import json
import M5
import lvgl as lv
import m5ui


def record(method, size, ok, value, oracle):
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "lvgl", "method": method, "payload_size": size,
        "status": "STATE_PASS" if ok else "FAIL", "value": value,
        "oracle": oracle,
    }))


def run():
    M5.begin()
    m5ui.init()
    ops = lv.cache_ops_t({"compare_cb": lv.strcmp, "free_cb": lv.free})
    cache = lv.cache_class_lru_rb_count.create(4, 1, ops)
    cache.set_name("ALLOC-0018")
    for size in (0, 4, 8, 16, 64):
        entry = lv.cache_entry_alloc(size, cache)
        actual = (entry.get_node_size(), entry.get_ref(), entry.get_cache() == cache,
                  entry.is_invalid())
        initialized = actual == (size, 0, True, False)
        record("cache_entry_alloc", size, initialized, actual,
               "unmodified allocator result has the original payload size, zero references, exact owning cache and valid flag")
        if not initialized:
            # This repair is exclusively for safe cleanup after the FAIL row.
            # It never contributes an allocator or lifecycle PASS.
            entry.init(cache, size)
            entry.delete()
            print("CACHE_ENTRY_ALLOC_CLEANUP_REPAIR " + str(size))
            continue
        pointer = entry.get_data()
        roundtrip = lv.cache_entry_get_entry(pointer, size) == entry
        record("cache_entry_get_entry", size, roundtrip, roundtrip,
               "payload pointer plus requested size returns the untouched native trailing header")
        payload = bytes(pointer.__dereference__(size)) if size else b""
        record("cache_entry_alloc_zero_payload", size, payload == bytes(size), list(payload),
               "all original caller payload bytes are zero before any write")
        expected = bytes((index * 37 + size + 11) & 255 for index in range(size))
        if size:
            pointer.__dereference__(size)[:] = expected
        observed = bytes(entry.get_data().__dereference__(size)) if size else b""
        after = (entry.get_node_size(), entry.get_ref(), entry.get_cache() == cache,
                 entry.is_invalid())
        record("cache_entry_alloc_payload_write", size,
               observed == expected and after == actual, (list(observed), after),
               "full owned payload write preserves the separately initialized metadata")
        acquired = entry.acquire_data()
        refs = [entry.get_ref()]
        entry.inc_ref()
        refs.append(entry.get_ref())
        entry.release_data(None)
        refs.append(entry.get_ref())
        entry.dec_ref()
        refs.append(entry.get_ref())
        record("cache_entry_alloc_reference_lifecycle", size,
               refs == [1, 2, 1, 0] and lv.cache_entry_get_entry(acquired, size) == entry,
               refs, "actual acquire/increment/release/decrement retains original payload pointer")
        entry.delete()
        record("cache_entry_alloc_delete", size, True, None,
               "original allocation deleted without manual metadata repair; no pointer use follows")
    cache.destroy(None)
    m5ui.deinit()


try:
    run()
except Exception as error:
    record("cache_entry_alloc_fixture", None, False, repr(error),
           "finite owned allocator fixture must complete")
print("CACHE_ENTRY_ALLOC_DONE")
