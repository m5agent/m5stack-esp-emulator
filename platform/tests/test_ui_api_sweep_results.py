"""Guard UI result classification against false coverage claims."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SWEEP = Path(__file__).resolve().parents[2] / "tests/uiflow2/api_sweep"
sys.path.insert(0, str(SWEEP))
from check_ui_frame import check_frame
from summarize_ui_results import summarize, expand_members
from join_ui_native_results import join as join_native


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is required for PNG oracle tests")
class UiFrameOracleTests(unittest.TestCase):
    def png(self):
        from PIL import Image
        image = Image.new("RGB", (8, 8), (0, 0, 0))
        image.putpixel((3, 4), (255, 0, 0))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def test_nonempty_frame_cannot_satisfy_wrong_pixel(self):
        raw = self.png()
        self.assertEqual(check_frame(raw, {"kind": "pixels", "points": [[3, 4, 0xFF0000]]})["status"], "FRAME_PASS")
        self.assertEqual(check_frame(raw, {"kind": "pixels", "points": [[2, 4, 0xFF0000]]})["status"], "FAIL")
        self.assertEqual(check_frame(raw, {"kind": "pixels", "points": []})["status"], "FAIL")

    def test_outside_the_actual_board_frame_is_probe_error(self):
        result = check_frame(self.png(), {"kind": "pixels", "points": [[9, 4, 0xFF0000]]})
        self.assertEqual(result["status"], "ORACLE_OUT_OF_BOUNDS")
        self.assertEqual(result["dimensions"], [8, 8])

    def test_shape_description_does_not_become_pixel_pass(self):
        result = check_frame(self.png(), {"kind": "shape", "shape": "a triangle"})
        self.assertEqual(result["status"], "PENDING_FRAME_REVIEW")

    def test_qr_crop_must_belong_to_the_actual_frame(self):
        result = check_frame(self.png(), {"kind": "qr_decode", "text": "payload", "box": [0, 0, 9, 8]})
        self.assertEqual(result["status"], "ORACLE_OUT_OF_BOUNDS")


class UiCoverageClassificationTests(unittest.TestCase):
    def test_native_owner_alias_and_sdk_preimage_do_not_inherit_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            declaration = root / "native.json"
            declaration.write_text(json.dumps({"binding_sha256": "pinned", "module_functions": {}, "types": {
                "first": {"name": "obj", "own_methods": {"set_user_data": {"implementation_owner": "same_native_owner"}}},
                "alias": {"name": "image", "own_methods": {"set_user_data": {"implementation_owner": "same_native_owner"}}},
            }}))
            for lane, base, status in (("stock", None, "FAIL"),
                    ("preimage", "7ce5ca0744a27508913c4dd69dd06f30454fb27c54a920faf486d3350cf2267b", "FAIL"),
                    ("candidate", "candidate-image", "STATE_PASS")):
                folder = root / lane
                folder.mkdir()
                (folder / "report.json").write_text(json.dumps({"device_id": "cores3", "base_sha256": base,
                    "firmware_lane": "stock-frozen" if lane == "stock" else "caller-pinned-candidate"}))
                (folder / "serial.txt").write_text("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl.obj", "method": "set_user_data", "status": status}) + "\n")
            result = join_native([declaration], [root])
        counts = result["counts"]["cores3"]
        self.assertEqual(counts["reference-frozen-implementation"]["methods_with_FAIL"], 1)
        self.assertEqual(counts["matching-sdk-preimage"]["methods_with_FAIL"], 1)
        self.assertEqual(counts["candidate-firmware"]["methods_with_STATE_PASS"], 1)
        self.assertEqual(result["results"]["lvgl.image.set_user_data"]["observations"], [])

    def test_runtime_member_delta_does_not_restore_removed_api(self):
        sets = {"base": {"base": None, "members": [["get_x", "function", True], ["delete", "function", True]]},
                "child": {"base": "base", "removed": ["delete"], "members": [["set_x", "function", True]]}}
        self.assertEqual(set(expand_members(sets, "child")), {"get_x", "set_x"})

    def test_one_passing_argument_and_candidate_cannot_hide_default_failure(self):
        inventory = {"documented_surfaces": [{"api_path": "m5ui.M5Spinbox", "members": [{"name": "set_step", "kind": "method"}]}],
                     "runtime": {"surfaces": [], "member_sets": {}}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, lane, results in (
                ("default", "reference-frozen-implementation", [{"api_target": "m5ui.M5Spinbox", "method": "set_step", "argument_domain": "integer", "status": "FAIL"},
                                                               {"api_target": "m5ui.M5Spinbox", "method": "set_step", "argument_domain": "decimal", "status": "STATE_PASS"}]),
                ("candidate", "candidate-source-override", [{"api_target": "m5ui.M5Spinbox", "method": "set_step", "status": "STATE_PASS"}]),
            ):
                folder = root / label
                folder.mkdir()
                report = {"device_id": "cores3", "implementation_lane": lane, "cases": [{"label": "case", "execution_id": label, "results": results, "frame_oracles": []}]}
                (folder / "report.json").write_text(json.dumps(report))
            result = summarize(inventory, [root])
        row = result["results"]["m5ui.M5Spinbox.set_step"]
        self.assertEqual(row["devices"]["cores3"]["status"], "FAIL")
        self.assertEqual(row["devices"]["cardputer-adv"]["status"], "NOT_RUN")
        self.assertEqual(len(result["candidate_observations"]), 1)
        self.assertEqual(result["candidate_observations"][0]["result"]["status"], "STATE_PASS")


if __name__ == "__main__":
    unittest.main()
