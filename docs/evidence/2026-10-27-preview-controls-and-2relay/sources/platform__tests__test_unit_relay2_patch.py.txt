"""Compile the actual new observer; exercise independent channels and pad reads."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from unit_runtime import UnitError, UnitRegistry

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0044-unit-2relay-gpio.patch"


class Relay2ContractTests(unittest.TestCase):
    def test_read_only_two_wire_contract_and_per_host_admission(self):
        registry = UnitRegistry()
        unit = registry.unit("2relay")
        self.assertEqual(unit["sku"], "U131")
        self.assertEqual(unit["inputs"], {})
        self.assertEqual(unit["interface"]["address_7bit"], [])
        self.assertEqual(set(unit["outputs"]), {f"output-{n}-{kind}" for n in (1, 2) for kind in ("level", "transitions")})
        for host, port, pins in (("cores3", "port-a", (1, 2)), ("atoms3r", "port-a", (1, 2)),
                                 ("sticks3", "custom", (10, 9)), ("stopwatch", "grove", (11, 10))):
            # Port identities are catalog facts, independent of tuple ordering.
            ports = registry.hosts[host]["ports"]
            port = next(p["id"] for p in ports if (p.get("pins", {}).get("white"), p.get("pins", {}).get("yellow")) == pins
                        and p.get("physical_presence") == "main-device")
            row = registry.attachments(host, "qemu", [{"id": "relay2", "unit_id": "2relay", "port_id": port}])[0]
            self.assertEqual((row["pins"]["white"], row["pins"]["yellow"]), pins)
        for field in unit["outputs"]:
            with self.subTest(field=field), self.assertRaises(UnitError):
                registry.input_values("2relay", {field: True}, live=True)
        with self.assertRaises(UnitError):
            registry.attachments("core2", "qemu", [{"id": "relay2", "unit_id": "2relay", "port_id": "port-a"}])

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_actual_c_observer_keeps_channels_independent(self):
        patch = PATCH.read_text()
        # Both new functions are complete additions, so this tests their actual
        # patch bytes without relying on an untracked QEMU source checkout.
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static void get_relay2_output(")
        end = added.index("    } else if (u->kind == UNIT_RELAY2)")
        functions = added[start:end]
        source = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef struct Object { int unused; } Object;
typedef struct Visitor { bool result; } Visitor;
typedef struct Error { int unused; } Error;
typedef struct M5Unit { int white, yellow, relay2_previous[2]; uint64_t relay2_transitions[2], output_transitions; } M5Unit;
static int pads[49];
static int esp32_gpio_get_line(int pin) { assert(pin >= 0 && pin < 49); return pads[pin]; }
static void visit_type_bool(Visitor *v, const char *name, bool *value, Error **errp) { (void)name; (void)errp; v->result = *value; }
''' + functions + '''
static void write_pad(M5Unit *u, int pin, int value) { pads[pin] = value; relay2_output_changed(u, pin, value); }
int main(void) {
    int pairs[][2] = {{1,2},{10,9},{11,10}};
    for (unsigned host = 0; host < 3; host++) {
        M5Unit u = {.white=pairs[host][0], .yellow=pairs[host][1]};
        pads[u.white]=pads[u.yellow]=0;
        write_pad(&u,u.white,1); write_pad(&u,u.white,1);
        assert(u.relay2_transitions[0]==1 && u.relay2_transitions[1]==0);
        write_pad(&u,u.yellow,1); write_pad(&u,u.white,1);
        assert(u.relay2_transitions[0]==1 && u.relay2_transitions[1]==1);
        write_pad(&u,u.white,0); write_pad(&u,u.yellow,1);
        assert(u.relay2_transitions[0]==2 && u.relay2_transitions[1]==1);
        write_pad(&u,u.yellow,0); write_pad(&u,u.yellow,0);
        assert(u.relay2_transitions[0]==2 && u.relay2_transitions[1]==2 && u.output_transitions==4);
        relay2_output_changed(&u,48,1); assert(u.output_transitions==4);
        // Getters must read the actual supplied pad, not remembered callback
        // state or the other channel, even before another notification.
        for (int a=0;a<2;a++) for(int b=0;b<2;b++) {
            pads[u.white]=a; pads[u.yellow]=b; Visitor v;
            get_relay2_output(NULL,&v,"output-1-level",&u.white,NULL); assert(v.result==a);
            get_relay2_output(NULL,&v,"output-2-level",&u.yellow,NULL); assert(v.result==b);
        }
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "relay2.c"
            path.write_text(source)
            binary = path.with_suffix("")
            subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror", str(path), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
