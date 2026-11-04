"""Static public-API boundary only; no guest firmware is executed here."""
import ast
from pathlib import Path
import unittest


class CardputerKeyboardObserverBoundaryTest(unittest.TestCase):
    def test_irq_observer_uses_public_callbacks_and_state_only(self):
        source = Path(__file__).resolve().parents[2] / "tests/browser-qemu/uiflow_workbench/cardputer_keyboard_observer.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
