"""Finite native LVGL containers with explicit byte/order/reference oracles.

Only owned allocations are mutated. Callbacks receive a retained dictionary,
never a byte buffer; native strcmp is the red-black-tree key comparator.
"""
import json
import M5


def check(target, method, action, oracle, description):
    try:
        value = action()
        ok = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target if target else "lvgl", "method": method,
            "status": "STATE_PASS" if ok else "FAIL", "oracle": description,
            "value": value if isinstance(value, (bool, int, float, str, list, tuple)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target if target else "lvgl", "method": method,
            "status": "FAIL", "oracle": description, "error": repr(error)}))


def read(pointer, count=1):
    return bytes(pointer.__dereference__(count))


def put(pointer, payload):
    pointer.__dereference__(len(payload))[:] = payload
    return pointer


def arrays(lv):
    a = lv.array_t()
    size = lambda: lv.array_t.size(a)
    capacity = lambda: lv.array_t.capacity(a)
    values = lambda: list(read(a.front(), size())) if size() else []
    check("array_t", "init", lambda: (a.init(4, 1), (size(), capacity(), a.element_size))[1], lambda v: v == (0, 4, 1), "owned four-byte capacity starts empty")
    check("array_t", "size", size, lambda v: v == 0, "empty array length")
    check("array_t", "capacity", capacity, lambda v: v == 4, "explicit initial capacity")
    check("array_t", "is_empty", a.is_empty, bool, "new array is empty")
    check("array_t", "push_back", lambda: (a.push_back(b'A'), a.push_back(b'B'), values())[-1], lambda v: v == [65, 66], "ordered byte append")
    check("array_t", "front", lambda: list(read(a.front())), lambda v: v == [65], "first appended byte")
    check("array_t", "back", lambda: list(read(a.back())), lambda v: v == [66], "last appended byte")
    check("array_t", "at", lambda: list(read(a.at(1))), lambda v: v == [66], "indexed second byte")
    check("array_t", "assign", lambda: (a.assign(1, b'C'), values())[1], lambda v: v == [65, 67], "indexed assignment changes only byte one")
    check("array_t", "resize", lambda: (a.resize(8), (capacity(), values())), lambda v: v == (True, (8, [65, 67])), "capacity growth preserves data")
    copied = lv.array_t()
    copied.init(1, 1)
    check("array_t", "copy", lambda: (copied.copy(a), list(read(copied.front(), lv.array_t.size(copied))))[1], lambda v: v == [65, 67], "independent allocated copy")
    check("array_t", "concat", lambda: (a.concat(copied), values())[1], lambda v: v == [65, 67, 65, 67], "concatenation preserves both sequences")
    check("array_t", "remove", lambda: (a.remove(1), values())[1], lambda v: v == [65, 65, 67], "remove shifts trailing elements")
    check("array_t", "erase", lambda: (a.erase(0, 2), values())[1], lambda v: v == [67], "half-open range erasure")
    check("array_t", "shrink", lambda: (a.shrink(), (capacity(), values()))[1], lambda v: v == (1, [67]), "sparse owned buffer shrinks to element count")
    check("array_t", "is_full", a.is_full, bool, "one element fills one capacity")
    check("array_t", "clear", lambda: (a.clear(), size(), a.is_empty())[1:], lambda v: v == (0, True), "logical clear resets size")
    check("array_t", "deinit", lambda: (a.deinit(), (size(), capacity()))[1], lambda v: v == (0, 0), "owned data released and counters zeroed")
    copied.deinit()
    external, backing = lv.array_t(), bytearray(4)
    check("array_t", "init_from_buf", lambda: (external.init_from_buf(backing, 4, 1), external.push_back(b'Z'), list(backing), external.inner_alloc)[2:], lambda v: v == ([90, 0, 0, 0], False), "external byte buffer receives native write without ownership transfer")
    external.deinit()


def circles(lv):
    c = lv.circle_buf_create(3, 1)
    check("", "circle_buf_create", lambda: (c.capacity(), c.size()), lambda v: v == (3, 0), "actual owned native constructor returns empty three-slot ring")
    backing = bytearray(4)
    external = lv.circle_buf_create_from_buf(backing, 4, 1)
    check("", "circle_buf_create_from_buf", lambda: (external.write(b'Q'), list(backing), external.capacity(), external.size())[1:], lambda v: v == ([81, 0, 0, 0], 4, 1), "native external-buffer constructor routes writes into exact caller-owned bytes")
    external.destroy()
    array_backing = bytearray(4)
    external_array = lv.array_t()
    external_array.init_from_buf(array_backing, 4, 1)
    from_array = lv.circle_buf_create_from_array(external_array)
    check("", "circle_buf_create_from_array", lambda: (from_array.write(b'R'), list(array_backing), from_array.capacity(), from_array.size())[1:], lambda v: v == ([82, 0, 0, 0], 4, 1), "native array wrapper shares explicit external storage; no owned-array ownership-transfer claim")
    from_array.destroy()
    external_array.deinit()
    check("circle_buf_t", "capacity", c.capacity, lambda v: v == 3, "explicit capacity")
    check("circle_buf_t", "size", c.size, lambda v: v == 0, "new ring empty")
    check("circle_buf_t", "remain", c.remain, lambda v: v == 3, "all slots initially free")
    check("circle_buf_t", "is_empty", c.is_empty, bool, "new ring empty predicate")
    check("circle_buf_t", "write", lambda: (c.write(b'A'), c.write(b'B'), c.size())[-1], lambda v: v == 2, "two real writes advance tail")
    check("circle_buf_t", "head", lambda: list(read(c.head())), lambda v: v == [65], "head identifies next read byte")
    put(c.tail(), b'C')
    check("circle_buf_t", "tail", lambda: list(read(c.tail())), lambda v: v == [67], "tail pointer addresses next writable slot")
    out = bytearray(1)
    check("circle_buf_t", "peek", lambda: (c.peek(out), list(out), c.size())[1:], lambda v: v == ([65], 2), "peek leaves length unchanged")
    check("circle_buf_t", "peek_at", lambda: (c.peek_at(1, out), list(out))[1], lambda v: v == [66], "indexed peek second byte")
    check("circle_buf_t", "read", lambda: (c.read(out), list(out), c.size())[1:], lambda v: v == ([65], 1), "read consumes first byte")
    check("circle_buf_t", "skip", lambda: (c.skip(), c.size())[1], lambda v: v == 0, "skip consumes remaining byte")
    calls, data = [], {"nonce": "RING"}
    def fill(buffer, length, index, user_data):
        assert user_data.__cast__()["nonce"] == "RING" and length == 1
        put(buffer, bytes([70 + index]))
        calls.append(index)
        return True
    check("circle_buf_t", "fill", lambda: (c.fill(3, fill, data), calls, list(read(c.head()))), lambda v: v == (3, [0, 1, 2], [70]), "callback fills real ring slots with dictionary userdata")
    check("circle_buf_t", "is_full", c.is_full, bool, "three callback elements fill capacity")
    check("circle_buf_t", "reset", lambda: (c.reset(), c.size(), c.is_empty())[1:], lambda v: v == (0, True), "reset drops queued elements")
    check("circle_buf_t", "resize", lambda: (c.resize(5), c.capacity(), c.size())[1:], lambda v: v == (5, 0), "resize reinitializes empty ring capacity")
    check("circle_buf_t", "destroy", c.destroy, lambda v: v is None, "owned ring destruction returns; no pointer access follows")


def lists(lv):
    ll, other = lv.ll_t(), lv.ll_t()
    ll.init(4)
    other.init(4)
    seq = lambda obj: list_values(obj)
    def insert(name, value, *args):
        node = getattr(ll, name)(*args)
        put(node, bytes([value, 0, 0, 0]))
        return node
    check("ll_t", "init", lambda: (ll.get_len(), ll.n_size), lambda v: v == (0, 4), "four-byte native nodes start empty")
    check("ll_t", "is_empty", ll.is_empty, bool, "empty linked list")
    a = insert("ins_head", 10)
    check("ll_t", "ins_head", lambda: seq(ll), lambda v: v == [10], "head insertion byte")
    b = insert("ins_tail", 30)
    check("ll_t", "ins_tail", lambda: seq(ll), lambda v: v == [10, 30], "tail insertion order")
    middle = insert("ins_prev", 20, b)
    check("ll_t", "ins_prev", lambda: seq(ll), lambda v: v == [10, 20, 30], "insertion before tail")
    check("ll_t", "get_head", lambda: read(ll.get_head())[0], lambda v: v == 10, "head payload")
    check("ll_t", "get_tail", lambda: read(ll.get_tail())[0], lambda v: v == 30, "tail payload")
    check("ll_t", "get_next", lambda: read(ll.get_next(a))[0], lambda v: v == 20, "next link")
    check("ll_t", "get_prev", lambda: read(ll.get_prev(b))[0], lambda v: v == 20, "previous link")
    check("ll_t", "get_len", ll.get_len, lambda v: v == 3, "three allocated nodes")
    check("ll_t", "move_before", lambda: (ll.move_before(b, a), seq(ll))[1], lambda v: v == [30, 10, 20], "tail node moved ahead of head")
    check("ll_t", "chg_list", lambda: (ll.chg_list(other, middle, True), seq(ll), seq(other))[1:], lambda v: v == ([30, 10], [20]), "node moves between two owned lists")
    check("ll_t", "remove", lambda: (ll.remove(a), seq(ll))[1], lambda v: v == [30], "unlink leaves other node intact")
    lv.free(a)
    check("ll_t", "clear", lambda: (ll.clear(), ll.get_len(), ll.is_empty())[1:], lambda v: v == (0, True), "clear frees remaining owned nodes")
    check("ll_t", "clear_custom", lambda: (other.clear_custom(None), other.get_len(), other.is_empty())[1:], lambda v: v == (0, True), "documented NULL cleanup performs native default unlink/free")


def list_values(ll):
    result, node = [], ll.get_head()
    while node is not None:
        result.append(read(node)[0])
        node = ll.get_next(node)
        assert len(result) <= 8
    return result


def trees(lv):
    tree = lv.rb_t()
    check("rb_t", "init", lambda: tree.init(lv.strcmp, 4), bool, "native strcmp comparator with owned four-byte null-terminated keys")
    nodes = {}
    for key in (b'B\0\0\0', b'A\0\0\0', b'C\0\0\0'):
        node = tree.insert(key)
        put(node.data, key)
        nodes[key[0]] = node
    check("rb_t", "insert", lambda: [read(tree.find(bytes([k, 0, 0, 0])).data)[0] for k in (65, 66, 67)], lambda v: v == [65, 66, 67], "three inserted payloads searchable in sorted key domain")
    check("rb_t", "find", lambda: (read(tree.find(b'B\0').data)[0], tree.find(b'Z\0') is None), lambda v: v == (66, True), "present and absent keys")
    check("rb_t", "minimum", lambda: read(tree.minimum().data)[0], lambda v: v == 65, "smallest ordered key")
    check("rb_t", "maximum", lambda: read(tree.maximum().data)[0], lambda v: v == 67, "largest ordered key")
    check("rb_node_t", "minimum_from", lambda: (read(nodes[66].minimum_from().data)[0], read(nodes[65].minimum_from().data)[0]), lambda v: v == (65, 65), "native root and leaf subtree minima in independent three-key A B C tree")
    check("rb_node_t", "maximum_from", lambda: (read(nodes[66].maximum_from().data)[0], read(nodes[67].maximum_from().data)[0]), lambda v: v == (67, 67), "native root and leaf subtree maxima in independent three-key A B C tree")
    def remove_node():
        data = tree.remove_node(nodes[65])
        value = read(data)[0]
        lv.free(data)
        return value, tree.find(b'A\0') is None
    check("rb_t", "remove_node", remove_node, lambda v: v == (65, True), "remove node transfers owned data to caller then caller frees")
    def remove_key():
        data = tree.remove(b'B\0')
        value = read(data)[0]
        lv.free(data)
        return value, tree.find(b'B\0') is None
    check("rb_t", "remove", remove_key, lambda v: v == (66, True), "remove by key and free returned payload")
    check("rb_t", "drop_node", lambda: (tree.drop_node(nodes[67]), tree.root is None), lambda v: v == (True, True), "last node drop also frees payload")
    node = tree.insert(b'D\0\0\0')
    put(node.data, b'D\0\0\0')
    check("rb_t", "drop", lambda: (tree.drop(b'D\0'), tree.root is None), lambda v: v == (True, True), "drop by key removes owned last node")
    check("rb_t", "destroy", tree.destroy, lambda v: v is None, "empty tree destroys safely")


def iterators(lv, cache, data):
    # Use the cache's actual C iterator callback and LRU order. This avoids
    # inventing a Python callback bridge that the stock binding cannot provide.
    for key in (b'E\0\0\0', b'F\0\0\0', b'G\0\0\0'):
        entry = cache.add(key, data)
        cache.release(entry, data)
    iterator = cache.iter_create()
    out = bytearray(lv.cache_entry_get_size(4))
    check("iter_t", "get_context", lambda: read(iterator.get_context(), 4) == b'\0' * 4, bool, "real cache iterator starts with zeroed native list cursor")
    check("iter_t", "make_peekable", lambda: (iterator.make_peekable(3), iterator.peek(out), out[0])[1:], lambda v: v == (lv.RESULT.OK, 71), "peek buffering retains first actual LRU entry G")
    check("iter_t", "peek", lambda: (iterator.peek(out), out[0]), lambda v: v == (lv.RESULT.OK, 71), "repeated peek leaves first entry unconsumed")
    check("iter_t", "peek_advance", lambda: (iterator.peek_advance(), iterator.peek(out), out[0]), lambda v: v == (lv.RESULT.OK, lv.RESULT.OK, 70), "peek offset advances from G to F without consuming")
    check("iter_t", "peek_reset", lambda: (iterator.peek_reset(), iterator.peek(out), out[0]), lambda v: v == (lv.RESULT.OK, lv.RESULT.OK, 71), "peek reset returns to buffered G")
    def next_values():
        values = []
        for _ in range(3):
            assert iterator.next(out) == lv.RESULT.OK
            values.append(out[0])
        assert iterator.next(out) == lv.RESULT.INVALID
        return values
    check("iter_t", "next", next_values, lambda v: v == [71, 70, 69], "buffered and uncached elements follow actual G F E LRU order then end")
    check("iter_t", "destroy", iterator.destroy, lambda v: v is None, "owned native cursor and peek-ring allocation released")
    fresh = cache.iter_create()
    inspected = []
    check("iter_t", "inspect", lambda: (fresh.inspect(lambda element: inspected.append(read(element)[0])), inspected)[1], lambda v: v == [71, 70, 69], "public Python inspect callback must receive actual native elements; unsupported callback conversion is retained as FAIL")
    fresh.destroy()
    def python_next(instance, context, element):
        return lv.RESULT.INVALID
    check("", "iter_create", lambda: lv.iter_create(cache, len(out), 4, python_next), lambda v: v is not None, "public iterator creation with Python callback; missing generated callback bridge remains FAIL")
    cache.drop_all(data)


def caches(lv):
    # Initial cache is empty; placeholder native free is replaced before use.
    ops = lv.cache_ops_t({"compare_cb": lv.strcmp, "free_cb": lv.free})
    cache = lv.cache_class_lru_rb_count.create(4, 3, ops)
    data, created, freed = {"nonce": "CACHE"}, [], []
    def create(node, user_data):
        assert user_data.__cast__()["nonce"] == "CACHE"
        created.append(read(node)[0])
        return True
    def free(node, user_data):
        assert user_data.__cast__()["nonce"] == "CACHE"
        freed.append(read(node)[0])
    cache.set_create_cb(create, data)
    cache.set_free_cb(free, data)
    cache.set_compare_cb(lv.strcmp, data)
    check("cache_class_t", "create", lambda: (cache.get_max_size(data), cache.get_size(data)), lambda v: v == (3, 0), "native count-based LRU cache initially empty")
    check("cache_t", "set_compare_cb", lambda: cache.ops.compare_cb(b'A\0', b'B\0'), lambda v: v < 0, "assigned native strcmp compares independent ordered keys")
    check("cache_t", "set_name", lambda: (cache.set_name("owned-cache"), cache.get_name())[1], lambda v: v == "owned-cache", "name roundtrip")
    check("cache_t", "get_name", cache.get_name, lambda v: v == "owned-cache", "retained cache name")
    check("cache_t", "get_max_size", lambda: cache.get_max_size(data), lambda v: v == 3, "count limit")
    check("cache_t", "get_size", lambda: cache.get_size(data), lambda v: v == 0, "zero occupied entries")
    check("cache_t", "get_free_size", lambda: cache.get_free_size(data), lambda v: v == 3, "all count slots free")
    check("cache_t", "is_enabled", cache.is_enabled, bool, "positive capacity enables cache")
    entry = cache.acquire_or_create(b'A\0\0\0', data)
    check("cache_t", "set_create_cb", lambda: created, lambda v: v == [65], "registered Python callback executed with exact retained dictionary")
    check("cache_t", "acquire_or_create", lambda: (entry.get_ref(), read(entry.get_data())[0]), lambda v: v == (1, 65), "created cache entry contains requested key and one reference")
    second = cache.acquire(b'A\0', data)
    check("cache_t", "acquire", second.get_ref, lambda v: v == 2, "acquiring existing key increments actual reference count")
    check("cache_t", "release", lambda: (cache.release(second, data), entry.get_ref())[1], lambda v: v == 1, "release decrements native reference count")
    cache.release(entry, data)
    entry = cache.add(b'B\0\0\0', data)
    check("cache_t", "add", lambda: (entry.get_ref(), read(entry.get_data())[0], cache.get_size(data)), lambda v: v == (1, 66, 2), "explicit add stores distinct entry")
    cache.release(entry, data)
    check("cache_t", "drop", lambda: (cache.drop(b'B\0', data), cache.acquire(b'B\0', data) is None, list(freed))[1:], lambda v: v == (True, [66]), "drop removes unreferenced key and invokes free callback")
    check("cache_t", "set_free_cb", lambda: list(freed), lambda v: v == [66], "registered Python free callback observed actual eviction")
    check("cache_t", "evict_one", lambda: (cache.evict_one(data), cache.get_size(data)), lambda v: v == (True, 0), "evicts only remaining unreferenced entry")
    check("cache_t", "set_max_size", lambda: (cache.set_max_size(4, data), cache.get_max_size(data))[1], lambda v: v == 4, "new maximum count roundtrip")
    for key in (b'C\0\0\0', b'D\0\0\0'):
        item = cache.add(key, data)
        cache.release(item, data)
    check("cache_t", "reserve", lambda: (cache.reserve(3, data), cache.get_free_size(data))[1], lambda v: v >= 3, "reservation evicts until three slots available")
    iterator = cache.iter_create()
    check("cache_t", "iter_create", lambda: iterator is not None, bool, "native iterator allocated for remaining entries")
    if iterator is not None:
        iterator.destroy()
    check("cache_t", "drop_all", lambda: (cache.drop_all(data), cache.get_size(data))[1], lambda v: v == 0, "drop-all clears all unreferenced entries")
    iterators(lv, cache, data)
    # Cache-entry allocation owns a payload and trailing metadata header.
    check("", "cache_entry_get_size", lambda: [lv.cache_entry_get_size(n) for n in (0, 4, 8)], lambda v: v == [16, 20, 24], "actual ESP32 32-bit ABI entry header is sixteen bytes plus caller payload")
    e = lv.cache_entry_alloc(4, cache)
    check("", "cache_entry_alloc", lambda: (e.get_node_size(), e.get_ref(), e.get_cache() == cache), lambda v: v == (4, 0, True),
              "raw allocator must return initialized trailing metadata; stock pre-initialization bug remains FAIL rather than inherited from later manual init")
    check("cache_entry_t", "init", lambda: (e.init(cache, 4), e.get_ref(), e.get_node_size(), e.is_invalid())[1:], lambda v: v == (0, 4, False), "entry metadata initialization")
    put(e.get_data(), b'KEY\0')
    check("", "cache_entry_get_entry", lambda: (lv.cache_entry_get_entry(e.get_data(), 4) == e,
          lv.cache_entry_get_entry(e.get_data(), 4).get_cache() == cache), lambda v: v == (True, True),
          "actual payload-plus-size lookup returns the manually initialized owned trailing entry")
    check("cache_entry_t", "get_data", lambda: list(read(e.get_data(), 4)), lambda v: v == [75, 69, 89, 0], "payload distinct from trailing entry metadata")
    check("cache_entry_t", "get_node_size", e.get_node_size, lambda v: v == 4, "declared payload size")
    check("cache_entry_t", "set_node_size", lambda: (e.set_node_size(4), e.get_node_size())[1], lambda v: v == 4, "payload-size setter roundtrip without pointer relocation")
    check("cache_entry_t", "get_ref", e.get_ref, lambda v: v == 0, "new entry unreferenced")
    check("cache_entry_t", "inc_ref", lambda: (e.inc_ref(), e.get_ref())[1], lambda v: v == 1, "increment reference")
    check("cache_entry_t", "dec_ref", lambda: (e.dec_ref(), e.get_ref())[1], lambda v: v == 0, "decrement reference")
    e.inc_ref()
    check("cache_entry_t", "reset_ref", lambda: (e.reset_ref(), e.get_ref())[1], lambda v: v == 0, "reference reset")
    check("cache_entry_t", "set_invalid", lambda: (e.set_invalid(True), e.is_invalid())[1], bool, "invalid flag setter")
    check("cache_entry_t", "is_invalid", e.is_invalid, bool, "invalid flag getter")
    check("cache_entry_t", "set_cache", lambda: (e.set_cache(cache), e.get_cache().get_name())[1], lambda v: v == "owned-cache", "cache pointer setter roundtrip through name nonce")
    check("cache_entry_t", "get_cache", lambda: e.get_cache().get_name(), lambda v: v == "owned-cache", "owning cache pointer resolves nonce")
    check("cache_entry_t", "acquire_data", lambda: (list(read(e.acquire_data(), 4)), e.get_ref()), lambda v: v == ([75, 69, 89, 0], 1), "payload acquire increments actual metadata reference")
    check("cache_entry_t", "release_data", lambda: (e.release_data(None), e.get_ref())[1], lambda v: v == 0, "payload release decrements actual metadata reference")
    check("cache_entry_t", "delete", e.delete, lambda v: v is None, "owned payload and entry freed; no access follows")
    check("cache_t", "destroy", lambda: cache.destroy(data), lambda v: v is None, "empty owned cache destruction")


def run():
    try:
        import lvgl as lv
        import m5ui
    except ImportError as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": "containers", "status": "UNAVAILABLE_ON_DEVICE", "oracle": repr(error)}))
        return
    M5.begin()
    m5ui.init()
    for target, action in (("array_t", arrays), ("circle_buf_t", circles), ("ll_t", lists), ("rb_t", trees), ("cache_t", caches)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target, "method": "fixture", "status": "FAIL", "oracle": "owned native container setup", "error": repr(error)}))
    m5ui.deinit()


run()
print("LVGL_CONTAINERS_DONE")
