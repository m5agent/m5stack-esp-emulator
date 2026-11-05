# atoms3-lite UIFlow2 regression probe

Run this checked-in case with `tests/uiflow2/run_device_matrix.py --device atoms3-lite`
using the documented board runtime and its compatible official reference firmware.
The matrix derives the filesystem layout from the actual base image and preserves
its other filesystem entries. See the root test guide for native regression prerequisites.

The official firmware may route Python stdout/REPL to USB CDC. `boot.py` attaches
`machine.UART(0)` using `os.dupterm` and its RX notification so the original guest
program is observable through the emulated UART controller. It does not supply
host values, replace guest execution, or validate USB CDC. Missing UART output
alone is not a pre-REPL boot-hang verdict; inspect same-run controller/frame state.

The original main program and functional markers remain the oracle. The UI
matrix also requires the declared input and pixel/frame assertions. Virtual-device
results cover the exact image/runtime only; physical properties are not tested.
