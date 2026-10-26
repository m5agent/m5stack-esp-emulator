import io
import sys
from probe_logging import emit

try:
    import host_program
except Exception as error:
    emit("HOST_PROBE_FAIL", repr(error))
    trace = io.StringIO()
    sys.print_exception(error, trace)
    emit(trace.getvalue())
    raise
