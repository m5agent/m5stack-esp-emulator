import io
import sys
from probe_logging import emit

try:
    import pwm_route_program
except Exception as error:
    emit("PWMR_FAIL", repr(error))
    trace = io.StringIO()
    sys.print_exception(error, trace)
    emit(trace.getvalue())
    raise
