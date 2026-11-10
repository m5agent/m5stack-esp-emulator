"""Host controls for the public-API observer; no guest firmware is executed."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


OBSERVER = (Path(__file__).resolve().parents[2] / "tests/browser-qemu/uiflow_workbench"
            / "cardputer_keyboard_observer.py")


class CardputerKeyboardObserverBoundaryTest(unittest.TestCase):
    def test_irq_observer_uses_public_callbacks_and_state_only(self):
        tree = ast.parse(OBSERVER.read_text(encoding="utf-8"))
        keyboard_calls = [node for node in ast.walk(tree)
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                          and isinstance(node.func.value, ast.Name) and node.func.value.id == "keyboard"]
        self.assertEqual({node.func.attr for node in keyboard_calls},
                         {"get_key", "is_key_pressed", "is_pressed", "set_callback", "deinit"})
        callback = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "key_event")
        callback_reads = [node for node in ast.walk(callback) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute) and node.func.attr == "get_key"]
        self.assertEqual(len(callback_reads), 1)
        self.assertEqual(sum(node.func.attr == "get_key" for node in keyboard_calls), 1)
        forbidden_imports = {"machine", "micropython", "driver", "tca8418"}
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertFalse(imported & forbidden_imports)
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__")
                             for node in ast.walk(tree)))

    def test_callback_captures_only_observed_state_before_serial_output(self):
        tree = ast.parse(OBSERVER.read_text(encoding="utf-8"))
        functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
                               type_ignores=[])
        program = compile(functions, str(OBSERVER), "exec")
        for initial_press in (True, False):
            with self.subTest(initial_press=initial_press):
                output = []
                state = {46: initial_press, 101: False}
                state_reads = []
                key_codes = iter((46, None))

                def read_state(code):
                    state_reads.append(code)
                    return state[code]

                keyboard = SimpleNamespace(is_key_pressed=read_state,
                                           get_key=lambda: next(key_codes))

                def serial_write(line):
                    state[46] = False
                    output.append(json.loads(line.split(" ", 1)[1]))

                observer = {"keyboard": keyboard, "json": json, "print": serial_write,
                            "time": SimpleNamespace(ticks_ms=lambda: 100),
                            "KEY_CODES": [46, 101], "RUN_NONCE": "host-control", "sequence": 0,
                            "previous": {46: False, 101: False}, "pressed_codes": set(),
                            "callback_count": 0, "pending": []}
                exec(program, observer)
                observer["sample_active_states"]()
                self.assertEqual(state_reads, [])
                observer["key_event"](keyboard)
                self.assertEqual(output, [])
                self.assertEqual(state_reads, [46, 101])
                observer["flush_events"]()
                observer["sample_active_states"]()
                observer["sample_active_states"]()
                observer["flush_events"]()
                self.assertEqual(state_reads, [46, 101, 46] if initial_press else [46, 101])
                self.assertEqual(output[0]["codes"], [46])
                self.assertEqual(output[0]["callback_count"], 1)
                self.assertEqual([row["pressed"] for row in output[1:]],
                                 [True, False] if initial_press else [])
                self.assertEqual([row["seq"] for row in output], list(range(1, len(output) + 1)))
                self.assertTrue(all(row["nonce"] == "host-control" for row in output))


if __name__ == "__main__":
    unittest.main()
