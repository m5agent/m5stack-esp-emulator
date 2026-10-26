import io
import sys
from probe_logging import emit

try:
    import sensor_probe
except Exception as error:
    emit("SENSOR_PROBE_FAIL", repr(error))
    buffer = io.StringIO()
    sys.print_exception(error, buffer)
    emit(buffer.getvalue())
