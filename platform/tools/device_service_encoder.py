"""Board input adapter for the native Dial quadrature source."""

from device_service_errors import ServiceError


ENCODER_PATH = "/machine/encoder"
MIN_DETENTS = -4096
MAX_DETENTS = 4096
MAX_DELTA = 128
EDGES_PER_DETENT = 4


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


def rotate_encoder(session, delta: int) -> dict[str, int]:
    """Schedule physical detents. The caller holds the session input lock."""
    delta = validate_encoder_delta(delta)
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
    session._qmp_call(
        "qom-set", path=ENCODER_PATH, property="detents", value=next_target
    )
    return {
        "delta": delta,
        "target_detents": next_target,
        "previous_detents": delivered,
        "previous_gpio_edges": edges,
    }
