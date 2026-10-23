set pagination off
set confirm off
python
import os
elf = os.environ.get(
    "M5_NATIVE_BT_ELF",
    ".work/uiflow2-core2-symbols/micropython.elf",
)
gdb.execute(f"file {elf}")
import sys
sys.path.insert(0, os.path.join(os.getcwd(), "platform/tools"))
sys.path.insert(0, os.path.join(os.getcwd(), "tests/uiflow2/core2_radio_probe"))
import native_vhci_bridge
native_vhci_bridge.start()
end
continue
