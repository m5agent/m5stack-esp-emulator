"""Session-scoped Unit wiring and QOM transport.

This module validates host intent. Chip protocols execute inside QEMU; a state
read always queries that guest, never a Python copy of previously sent input.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
UNIT_ROOT = ROOT / "platform/units"
INSTANCE_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
MAX_ATTACHMENTS = 16


class UnitError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _load(path: Path, raw: bytes | None = None) -> dict:
    value = json.loads(raw if raw is not None else path.read_bytes())
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise UnitError("invalid_unit_catalog", f"invalid schema in {path.name}", 500)
    return value


def scalar_value(value: Any, schema: dict, field: str) -> Any:
    kind = schema.get("type")
    if kind == "boolean":
        valid = isinstance(value, bool)
    elif kind in {"integer", "number"}:
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError):
            finite = False
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and finite
            and (kind != "integer" or isinstance(value, int))
        )
    elif kind == "string":
        valid = isinstance(value, str) and len(value) <= schema.get("maxLength", 256)
    elif kind == "array":
        if not isinstance(value, list) or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 4096):
            raise UnitError("invalid_unit_input", f"{field} has an invalid array length")
        return [scalar_value(item, schema.get("items", {}), f"{field}[{index}]") for index, item in enumerate(value)]
    else:
        raise UnitError("invalid_unit_schema", f"unsupported type for {field}", 500)
    if not valid:
        raise UnitError("invalid_unit_input", f"{field} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise UnitError("invalid_unit_input", f"{field} is outside the allowed values")
    if kind == "string" and schema.get("pattern") and not re.fullmatch(schema["pattern"], value):
        raise UnitError("invalid_unit_input", f"{field} has an invalid encoding")
    if kind in {"integer", "number"} and (
        ("minimum" in schema and value < schema["minimum"])
        or ("maximum" in schema and value > schema["maximum"])
    ):
        raise UnitError("invalid_unit_input", f"{field} is outside the supported range")
    return value


class UnitRegistry:
    def __init__(self, root: Path = UNIT_ROOT, *, contract: dict | None = None):
        self.root = root
        if contract is not None:
            if not isinstance(contract, dict) or contract.get("schema_version") != 1 or any(
                not isinstance(contract.get(field), dict) for field in ("units", "profiles", "source_hashes")
            ):
                raise UnitError("invalid_unit_contract", "unsupported persisted Unit contract", 500)
            for unit_id, unit in contract["units"].items():
                profile = contract["profiles"].get(unit_id)
                if not isinstance(unit, dict) or not isinstance(profile, dict) or any(
                    not isinstance(unit.get(field), dict) for field in ("inputs", "outputs")
                ) or any(not isinstance(profile.get(field), dict) for field in ("inputs", "state")):
                    raise UnitError("invalid_unit_contract", "incomplete persisted Unit contract", 500)
            self.units = copy.deepcopy(contract["units"])
            self.profiles = copy.deepcopy(contract["profiles"])
            self.source_hashes = copy.deepcopy(contract["source_hashes"])
            self.fixtures = copy.deepcopy(contract.get("fixtures", {}))
            self.hosts = {}
            return
        sources = {
            filename: (root / filename).read_bytes()
            for filename in ("catalog.json", "host-ports.json", "runtime-profiles.json")
        }
        self.catalog = _load(root / "catalog.json", sources["catalog.json"])
        self.host_catalog = _load(root / "host-ports.json", sources["host-ports.json"])
        self.profiles = _load(root / "runtime-profiles.json", sources["runtime-profiles.json"])["units"]
        self.source_hashes = {
            filename: hashlib.sha256(raw).hexdigest()
            for filename, raw in sources.items()
        }
        self.units = {row["id"]: row for row in self.catalog["units"]}
        self.hosts = {row["device_id"]: row for row in self.host_catalog["hosts"]}
        if len(self.units) != len(self.catalog["units"]):
            raise UnitError("invalid_unit_catalog", "duplicate Unit id", 500)
        if len(self.hosts) != len(self.host_catalog["hosts"]):
            raise UnitError("invalid_unit_catalog", "duplicate host id", 500)

    def freeze(self, unit_ids: list[str]) -> dict:
        source_hashes = dict(self.source_hashes)
        fixtures = {}
        if any(unit_id in {"angle", "light"} for unit_id in unit_ids):
            relative = "fixtures/esp32s3-adc-calibration.json"
            raw = (self.root / relative).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            fixtures["esp32s3-adc"] = {"raw_utf8": raw.decode("utf-8"), "sha256": digest}
            source_hashes[relative] = digest
        return {
            "schema_version": 1, "source_hashes": source_hashes, "fixtures": fixtures,
            "units": {unit_id: copy.deepcopy(self.units[unit_id]) for unit_id in unit_ids},
            "profiles": {unit_id: copy.deepcopy(self.profiles[unit_id]) for unit_id in unit_ids},
        }

    def unit(self, unit_id: str) -> dict:
        if unit_id not in self.units:
            raise UnitError("unknown_unit", f"unknown Unit: {unit_id}", 404)
        row = copy.deepcopy(self.units[unit_id])
        row["runtime"] = copy.deepcopy(self.profiles.get(unit_id, {
            "status": "planned", "blocker": "controller data plane not implemented",
        }))
        # Keep the original protocol-research snapshot explicit. Runtime
        # profiles (or the session's frozen copy) own all current status aliases.
        row["research_snapshot"] = {
            "scope": "protocol research only; not current runtime capability",
            "model_status": self.units[unit_id].get("model_status"),
            "runtime_status": self.units[unit_id].get("runtime", {}).get("status"),
            "blocker": self.units[unit_id].get("blocker"),
        }
        row["model_status"] = row["runtime"]["status"]
        row["blocker"] = row["runtime"].get("blocker", "")
        return row

    def inventory(self, device_id: str | None = None) -> dict:
        if device_id is not None and device_id not in self.hosts:
            raise UnitError("unknown_device", f"unknown host: {device_id}", 404)
        return {
            "schema_version": 1,
            "units": [self.unit(unit_id) for unit_id in self.units],
            "hosts": copy.deepcopy(
                [self.hosts[device_id]] if device_id else list(self.hosts.values())
            ),
            "contract": "one session, one guest, controller-backed Unit state",
        }

    def input_values(self, unit_id: str, payload: Any, *, live: bool = False) -> dict:
        unit = self.unit(unit_id)
        fields = unit.get("inputs", {})
        if not isinstance(payload, dict):
            raise UnitError("invalid_unit_input", "Unit input must be an object")
        if not isinstance(fields, dict):
            raise UnitError("invalid_unit_schema", "Unit inputs must be a mapping", 500)
        unknown = sorted(set(payload) - set(fields))
        if unknown:
            raise UnitError("invalid_unit_input", f"unknown input fields: {', '.join(unknown)}")
        profile_fields = self.profiles.get(unit_id, {}).get("inputs", {})
        limit = self.profiles.get(unit_id, {}).get("max_live_input_fields")
        if live and limit is not None and len(payload) > limit:
            raise UnitError(
                "invalid_unit_input", f"{unit_id} accepts at most {limit} live input field per request; submit separate requests",
            )
        values = {}
        for field, value in payload.items():
            if field not in profile_fields:
                raise UnitError(
                    "unit_input_not_supported", f"{unit_id}.{field} has no controller input", 409,
                )
            if live and (fields[field].get("creation_only") or profile_fields[field].get("creation_only")):
                raise UnitError(
                    "unit_input_creation_only", f"{unit_id}.{field} is frozen after creation; create a new session to select it", 409,
                )
            values[field] = scalar_value(value, fields[field], field)
        return values

    def attachments(self, device_id: str, runtime: str, value: Any) -> list[dict]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > MAX_ATTACHMENTS:
            raise UnitError("invalid_units", f"units must be a list of at most {MAX_ATTACHMENTS}")
        if not value:
            return []
        if runtime not in {"qemu", "qemu-wifi", "qemu-ble", "qemu-unified"}:
            raise UnitError("units_not_supported", "Units require a QEMU guest", 409)
        host = self.hosts.get(device_id)
        if host is None:
            raise UnitError("units_not_supported", "host port wiring is not registered", 409)
        ports = {port["id"]: port for port in host["ports"]}
        rows, occupied = {}, set()
        for row in value:
            if not isinstance(row, dict) or set(row) - {"id", "unit_id", "port_id", "initial", "parent_id"}:
                raise UnitError("invalid_units", "invalid Unit attachment fields")
            instance, unit_id, port_id = row.get("id"), row.get("unit_id"), row.get("port_id")
            if not isinstance(instance, str) or not INSTANCE_ID.fullmatch(instance):
                raise UnitError("invalid_units", "Unit instance id must be a short lowercase identifier")
            if instance in rows:
                raise UnitError("invalid_units", "Unit instance ids must be unique")
            if not isinstance(unit_id, str) or not isinstance(port_id, str):
                raise UnitError("invalid_units", "unit_id and port_id are required strings")
            self.unit(unit_id)
            profile = self.profiles.get(unit_id, {})
            if profile.get("status") not in {"implemented", "validated"}:
                raise UnitError("runtime_model_gap", profile.get("blocker", f"{unit_id} is not implemented"), 409)
            if device_id not in profile.get("hosts", []):
                raise UnitError("runtime_model_gap", f"{unit_id} has no controller wiring for {device_id}", 409)
            parent = row.get("parent_id")
            if parent is not None and (not isinstance(parent, str) or not INSTANCE_ID.fullmatch(parent)):
                raise UnitError("invalid_units", "parent_id must identify an attached HUB")
            connector = (parent, port_id)
            if connector in occupied:
                raise UnitError("unit_port_conflict", "each physical connector accepts only one Unit", 409)
            occupied.add(connector)
            rows[instance] = {**row, "initial": self.input_values(unit_id, row.get("initial", {}))}

        resolved, visiting = {}, set()

        def resolve(instance: str) -> dict:
            if instance in resolved:
                return resolved[instance]
            if instance in visiting:
                raise UnitError("invalid_unit_topology", "Unit attachment topology contains a cycle")
            visiting.add(instance)
            row = rows[instance]
            parent, port_id = row.get("parent_id"), row["port_id"]
            if parent is not None:
                if parent not in rows or rows[parent]["unit_id"] != "hub":
                    raise UnitError("invalid_unit_topology", "parent_id must reference an attached passive HUB")
                if port_id not in {"grove-1", "grove-2", "grove-3"}:
                    raise UnitError("unit_port_not_supported", "HUB output must be grove-1, grove-2 or grove-3", 409)
                upstream = resolve(parent)
                pins = upstream["pins"]
                visual_port = f"{upstream['visual_port']}/{port_id}" if upstream.get("visual_port") else None
            else:
                port = ports.get(port_id)
                if not port or port.get("wiring_status") != "confirmed":
                    raise UnitError("unit_port_not_supported", "selected physical port wiring is not confirmed", 409)
                if port.get("physical_presence") != "main-device":
                    raise UnitError("unit_port_not_supported", "port requires an accessory configuration not attached to this host", 409)
                admitted_units = port.get("admitted_unit_ids")
                if admitted_units is not None and row["unit_id"] not in admitted_units:
                    raise UnitError(
                        "unit_port_not_supported",
                        f"{row['unit_id']} is not admitted on {port_id}",
                        409,
                    )
                pins, visual_port = port.get("pins", {}), port.get("visual_port")
            if any(type(pins.get(wire)) is not int or pins[wire] < 0 for wire in ("yellow", "white")):
                raise UnitError("unit_port_not_supported", "host pin mapping is incomplete", 409)
            result = {
                "id": instance, "unit_id": row["unit_id"], "port_id": port_id,
                "pins": {wire: pins[wire] for wire in ("yellow", "white")},
                "visual_port": visual_port, "initial": row["initial"],
                **({"parent_id": parent} if parent is not None else {}),
            }
            resolved[instance] = result
            visiting.remove(instance)
            return result

        for instance in rows:
            resolve(instance)
        buses: dict[tuple[int, int], list[dict]] = {}
        for row in resolved.values():
            if row["unit_id"] != "hub":
                pins = row["pins"]
                buses.setdefault((pins["yellow"], pins["white"]), []).append(row)
        for leaves in buses.values():
            if len(leaves) < 2:
                continue
            addresses: set[int] = set()
            for leaf in leaves:
                interface = self.units[leaf["unit_id"]]["interface"]
                if interface["bus"] != "i2c":
                    raise UnitError("unit_bus_conflict", "parallel GPIO, ADC, PWM, RMT and UART attachments require an explicit contention model", 409)
                profile = self.profiles[leaf["unit_id"]]
                address_input = profile.get("address_input")
                if address_input:
                    current = {
                        leaf["initial"].get(
                            address_input,
                            profile.get("default_address_7bit"),
                        )
                    }
                else:
                    current = set(interface.get("address_7bit", []))
                if addresses & current:
                    raise UnitError("unit_address_conflict", "passive HUB cannot separate duplicate I2C addresses", 409)
                addresses.update(current)
        # DFS inserts parents first, so runtime and visual attachment order agree.
        return list(resolved.values())

    def state(self, attachments: list[dict], qom: Callable) -> list[dict]:
        states = []
        for attachment in attachments:
            profile = self.profiles[attachment["unit_id"]]
            properties, errors = {}, {}
            for field, descriptor in profile.get("state", {}).items():
                path = f"/machine/units/{attachment['id']}{descriptor.get('path', '')}"
                try:
                    properties[field] = qom(path, descriptor["property"])
                except Exception as error:
                    errors[field] = str(error)
            states.append({
                **copy.deepcopy(attachment), "source": "guest-qom",
                "available": bool(properties) and not errors,
                "properties": properties, "errors": errors,
            })
        return states


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--device")
    args = parser.parse_args()
    registry = UnitRegistry()
    inventory = registry.inventory(args.device)
    if args.check:
        for unit in inventory["units"]:
            for direction in ("inputs", "outputs"):
                if not isinstance(unit.get(direction), dict):
                    raise UnitError("invalid_unit_catalog", f"{unit['id']} {direction} must be a mapping", 500)
            if unit["runtime"]["status"] != "validated" and not unit["runtime"].get("blocker"):
                raise UnitError("invalid_unit_catalog", f"{unit['id']} requires an explicit runtime blocker", 500)
        print("UNIT_CATALOG_OK")
    else:
        print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
