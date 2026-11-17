"""Board input adapter for the native Dial quadrature source."""

from device_service_errors import ServiceError

ENCODER_PATH = "/machine/encoder"
MIN_DETENTS = -4096
MAX_DETENTS = 4096
MAX_DELTA = 128
EDGES_PER_DETENT = 4
FAST_EDGE_PERIOD_MS = 5
DEFAULT_EDGE_PERIOD_MS = 35
MAX_EDGE_PERIOD_MS = 100
PACED_MOTION_PROPERTY = "paced-detents"


def supports_rotary_encoder(spec, runtime: str) -> bool:
    return runtime == "qemu" and spec.id == "dial" and spec.machine == "m5dial"


def validate_encoder_delta(delta: object) -> int:
    if type(delta) is not int or not 1 <= abs(delta) <= MAX_DELTA:
        raise ServiceError(
            "invalid_input",
            f"encoder delta must be a non-zero integer within -{MAX_DELTA}..{MAX_DELTA}",
            400,
        )
    return delta


def validate_encoder_edge_period_ms(period: object) -> int:
    if type(period) is not int or not FAST_EDGE_PERIOD_MS <= period <= MAX_EDGE_PERIOD_MS:
        raise ServiceError(
            "invalid_input",
            f"encoder edge_period_ms must be an integer within "
            f"{FAST_EDGE_PERIOD_MS}..{MAX_EDGE_PERIOD_MS}",
            400,
        )
    return period


def rotate_encoder(session, delta: int, *, edge_period_ms: int | None = None) -> dict[str, int | str]:
    """Schedule physical detents. The caller holds the session input lock."""
    delta = validate_encoder_delta(delta)
    if edge_period_ms is not None:
        validate_encoder_edge_period_ms(edge_period_ms)
    if not supports_rotary_encoder(session.spec, session.runtime):
        raise ServiceError(
            "unsupported_input",
            "rotary encoder input requires a native Dial session",
            409,
        )

    def read(name: str) -> int:
        value = session._qmp_call(
            "qom-get", path=ENCODER_PATH, property=name
        ).get("return")
        if type(value) is not int:
            raise ServiceError(
                "qmp_error", f"unexpected Dial encoder {name} observation", 503
            )
        return value

    target = read("detents")
    delivered = read("delivered-detents")
    edges = read("gpio-edges")
    # An opposite target would replace the remaining movement in the model.
    # A raw QOM write can also leave target == delivered mid-detent.
    if target != delivered or edges % EDGES_PER_DETENT:
        raise ServiceError(
            "input_busy",
            "Dial encoder has pending physical movement",
            409,
            target_detents=target,
            delivered_detents=delivered,
        )
    next_target = target + delta
    if not MIN_DETENTS <= next_target <= MAX_DETENTS:
        raise ServiceError(
            "invalid_input",
            f"encoder target must stay within {MIN_DETENTS}..{MAX_DETENTS}",
            400,
        )
    properties = session._qmp_call("qom-list", path=ENCODER_PATH).get("return")
    if not isinstance(properties, list) or any(not isinstance(row, dict) for row in properties):
        raise ServiceError("qmp_error", "unexpected Dial encoder property list", 503)
    if any(row.get("name") == PACED_MOTION_PROPERTY for row in properties):
        selected_period = DEFAULT_EDGE_PERIOD_MS if edge_period_ms is None else edge_period_ms
        property_name = PACED_MOTION_PROPERTY
        value = {"target_detents": next_target, "edge_period_ms": selected_period}
    else:
        if edge_period_ms is not None:
            raise ServiceError(
                "unsupported_input",
                "this Dial runtime does not support a custom encoder edge period",
                409,
            )
        property_name, value = "detents", next_target
        selected_period = FAST_EDGE_PERIOD_MS
    session._qmp_call("qom-set", path=ENCODER_PATH, property=property_name, value=value)
    return {
        "delta": delta,
        "target_detents": next_target,
        "previous_detents": delivered,
        "previous_gpio_edges": edges,
        "edge_period_ms": selected_period,
        "completion": "queued",
    }
