set pagination off
set confirm off
file .work/uiflow2-core2-symbols/micropython.elf
python
import os
import sys
sys.path.insert(0, os.path.join(os.getcwd(), "platform/tools"))
sys.path.insert(0, os.path.join(os.getcwd(), "tests/uiflow2/core2_radio_probe"))
import native_vhci_bridge
native_vhci_bridge.start()
end
continue
