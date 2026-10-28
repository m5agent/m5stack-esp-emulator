"""Keep native factory/global functions inside the LVGL API denominator."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ui_native_binding_audit", ROOT / "tests/uiflow2/api_sweep/ui_native_bindings.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UiNativeBindingAuditTests(unittest.TestCase):
    def test_static_factories_and_instance_calls_are_both_classified(self):
        source = '''
MP_DEFINE_CONST_LV_FUN_OBJ_STATIC_VAR(timer_create_obj, 3, wrap_create, lv_timer_create);
MP_DEFINE_CONST_LV_FUN_OBJ_VAR(timer_pause_obj, 1, wrap_pause, lv_timer_pause);
static const mp_rom_map_elem_t lvgl_globals_table[] = {
 { MP_ROM_QSTR(MP_QSTR_timer_create), MP_ROM_PTR(&timer_create_obj) },
 { MP_ROM_QSTR(MP_QSTR_timer_t), MP_ROM_PTR(&timer_type) },
};
static const mp_rom_map_elem_t timer_locals_dict_table[] = {
 { MP_ROM_QSTR(MP_QSTR_pause), MP_ROM_PTR(&timer_pause_obj) },
 { MP_ROM_QSTR(MP_QSTR_create), MP_ROM_PTR(&timer_create_obj) },
};
MP_DEFINE_CONST_OBJ_TYPE(
 timer_type,
 MP_QSTR_timer_t,
 MP_TYPE_FLAG_NONE,
 locals_dict, &timer_locals_dict
);
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "m5stack/build-M5STACK_CoreS3/lv_mp.c"
            generated.parent.mkdir(parents=True)
            generated.write_text(source)
            result = MODULE.parse_bindings(root)
        factory = result["exports"]["timer_create"]
        self.assertEqual(factory["kind"], "function")
        self.assertEqual(factory["binding_kind"], "static")
        self.assertEqual(factory["implementation_owner"], "lv_timer_create")
        self.assertEqual(factory["minimum_binding_arity"], 3)
        self.assertEqual(MODULE.resolve_method(result, "lvgl.timer_t", "pause")["binding_kind"], "instance")
        self.assertEqual(MODULE.resolve_method(result, "lvgl.timer_t", "create")["binding_kind"], "static")


if __name__ == "__main__":
    unittest.main()
