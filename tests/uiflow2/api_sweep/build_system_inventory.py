#!/usr/bin/env python3
"""Inventory documented system/communication and optional accessory APIs.

Official source is a candidate denominator, not proof that an older stock
firmware exports it. Guest reflection and behavioral recipes remain separate.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

EXTERNAL = {"unit", "module", "base", "hat", "cap", "chain", "stamp", "stamplc", "addon"}
LIBRARIES = {"bleuart", "m5ble", "m5espnow", "requests2", "easysocket", "software", "modbus", "umqtt",
             "ezdata", "usb", "utility", "microdot", "iot_devices"}


def canonical_api(api, import_aliases=None):
    """Resolve verified import aliases; keep abstract implementation owners distinct."""
    api=re.sub(r"^(?:easysocket\.)?software\.easysocket\.(?:tcp_client|tcp_server|udp_client|udp_server)\.","easysocket.",api)
    api=api.replace("modbus.modbus.","modbus.",1)
    api=re.sub(r"^modbus\.(?:master|slave|tcp\.client|tcp\.server|rtu\.master|rtu\.slave)\.(Modbus(?:TCPClient|TCPServer|RTUMaster|RTUSlave))",r"modbus.\1",api)
    api=api.replace("umqtt.default.MQTTClient","umqtt.MQTTClient",1)
    api=api.replace("m5ble.M5BLE.","m5ble.m5ble.",1)
    api=api.replace("m5ble.m5ble.Device.client.","m5ble.m5ble.Client.",1)
    api=api.replace("m5ble.m5ble.Device.server.","m5ble.m5ble.Server.",1)
    api=api.replace("m5ble.connected_client_handle.","m5ble.m5ble.Server.Client.",1)
    api=api.replace("m5espnow.m5espnow.M5ESPNow","m5espnow.M5ESPNow",1)
    api=api.replace("image.Image.find_qrcodes.result","image.qrcode",1)
    api=api.replace("image.Qrcode","image.qrcode",1)
    api=api.replace("code_scanner.find_qrcodes.result","image.QRCode",1)
    if api in {"code_scanner.payload","code_scanner.type_name"}:
        api="image.QRCode."+api.rsplit(".",1)[1]
    api=api.replace("dl.detect_result","dl.DetectionResult",1)
    if api in {"dl.ObjectDetector.infer.negative","dl.HumanFaceRecognizer.recognize.negative"}:
        api=api.removesuffix(".negative")
    api={"requests2.request.data_file":"requests2.request",
         "ezdata.EzData.set.file":"ezdata.EzData.set",
         "ezdata.EzData.get.file_metadata":"ezdata.EzData.get",
         "network.WLAN.active.deactivate":"network.WLAN.active",
         "network.WLAN.ifconfig.set":"network.WLAN.ifconfig",
         "network.WLAN.reconnect":"network.WLAN.connect",
         "time.timezone.localtime":"time.timezone"}.get(api,api)
    if import_aliases:
        for source,target in sorted(import_aliases.items(),key=lambda item:-len(item[0])):
            if api==source or api.startswith(source+"."):
                return target+api[len(source):]
    return api


def audit_document(path, root, found):
    text=path.read_text(encoding="utf-8")
    relative=path.relative_to(root).as_posix()
    category=path.relative_to(root/"docs/source").parts[0]
    linked=re.findall(r"(?:<|:doc:`)(\.\./[^>`]+?)(?:\.html|`|>)",text)
    if found:return {"status":"PARSED_API_DIRECTIVES","basis":"RST and py-domain declarations with class ownership"}
    if category=="controllers":
        prose=re.sub(r"[\s#=\-]","",re.sub(r"^.*(?:include::|sku:).*$","",text,flags=re.MULTILINE))
        return {"status":"REVIEWED_DEVICE_GUIDE" if len(prose)>40 else "REVIEWED_PLACEHOLDER",
                "basis":"board overview, launcher instructions and shared API links; no independent API declarations",
                "shared_document_links":sorted(set(linked))}
    if category=="quick-reference":
        return {"status":"REVIEWED_EDITOR_WORKFLOW","basis":"host editor/USB workflow, no MicroPython callable declarations"}
    delegates={"software/easysocket.rst":["software/tcp.client.rst","software/tcp.server.rst","software/udp.client.rst","software/udp.server.rst"],
               "software/modbus.rst":["software/modbus.rtu.master.rst","software/modbus.rtu.slave.rst","software/modbus.tcp.client.rst","software/modbus.tcp.server.rst"],
               "software/umqtt.rst":["software/umqtt.default.rst"],
               "system/audio.rst":["system/audio.player.rst","system/audio.recorder.rst"],
               "system/bleuart.rst":["system/bleuart.client.rst","system/bleuart.server.rst"],
               "stamp/cam0308.rst":["advanced/camera.rst","advanced/image.rst"]}
    key=path.relative_to(root/"docs/source").as_posix()
    if key in delegates:
        return {"status":"REVIEWED_SHARED_API_DELEGATION","basis":"overview delegates to shared detailed API pages; APIs counted at their owner",
                "delegate_documents":["docs/source/"+name for name in delegates[key]]}
    if key=="unit/pahub.rst":
        return {"status":"REVIEWED_TOPOLOGY_GUIDE","basis":"I2C hub routing configuration, source API owned by unit.pahub.PAHUBUnit; no independent callable declared on this page",
                "source_owner":"m5stack/libs/unit/pahub.py"}
    raise ValueError("unreviewed document without API directives: "+relative)


def build(root):
    entries, sources, documents = {}, {}, []
    import_aliases={}
    for initializer in sorted((root/"m5stack/libs").rglob("__init__.py")):
        package=".".join(initializer.parent.relative_to(root/"m5stack/libs").parts)
        if package.split(".")[0] not in LIBRARIES|EXTERNAL:continue
        try:tree=ast.parse(initializer.read_text(encoding="utf-8"))
        except SyntaxError:continue
        for node in tree.body:
            if isinstance(node,ast.ImportFrom) and node.level==1 and node.module:
                for symbol in node.names:
                    public_name=symbol.asname or symbol.name
                    if not public_name.startswith("_") and public_name!="*":
                        import_aliases[package+"."+node.module+"."+symbol.name]=package+"."+public_name
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=="_attrs" for target in node.targets):
                try:attrs=ast.literal_eval(node.value)
                except (ValueError,TypeError):continue
                if isinstance(attrs,dict):
                    for symbol,module_path in attrs.items():
                        if isinstance(symbol,str) and isinstance(module_path,str):
                            import_aliases[package+"."+module_path+"."+symbol]=package+"."+symbol

    def reference(path):
        relative = path.relative_to(root).as_posix()
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return relative

    def add(api, signature, kind, path, line, scope, evidence):
        declared_api=api
        api=canonical_api(api,import_aliases)
        row = entries.setdefault(api, {"api": api, "kind": kind, "scope": scope,
            "signatures": [], "sources": [], "runtime_exports": "PENDING",
            "aliases":[],"owner":api.rsplit(".",1)[0] if kind!="constructor" else api,
            "results": {"cores3": "NOT_RUN", "cardputer-adv": "NOT_RUN"}})
        if declared_api!=api and declared_api not in row["aliases"]:row["aliases"].append(declared_api)
        if signature not in row["signatures"]:
            row["signatures"].append(signature)
        ref = f"{path}:{line}"
        if ref not in row["sources"]:
            row["sources"].append(ref)
        row["required_evidence"] = evidence
        row["recipe_id"] = ("selected-accessory" if scope == "optional-accessory" else
                            "local-clock" if api.startswith("time.") else
                            "wifi-lifecycle" if api.startswith("network.") else
                            "protocol-peer" if any(x in api.lower() for x in ("socket", "mqtt", "modbus", "ble", "espnow", "request")) else
                            "system-behavior")

    docs = root / "docs/source"
    for path in sorted(docs.rglob("*.rst")):
        category = path.relative_to(docs).parts[0]
        if category in {"hardware", "m5ui", "widgets"} or path.stem in {"index", "COPYRIGHT"}:
            continue
        relative = reference(path)
        if category=="contribute":
            documents.append({"path":relative,"scope":"contributor-workflow","api_count":0,
                "parser_status":"REVIEWED_NO_INDEPENDENT_DECLARATIONS","audit":{"status":"REVIEWED_CONTRIBUTOR_TEMPLATE",
                "basis":"Contributor instructions and fictitious documentation examples are not product API declarations."}})
            continue
        external = category in EXTERNAL
        scope = "optional-accessory" if external else "system-communication"
        stem = path.stem
        module = {"wlan.sta": "network", "wlan.ap": "network", "time": "time",
                  "audio.player": "audio", "audio.recorder": "audio", "m5ble": "m5ble",
                  "bleuart.client": "bleuart", "bleuart.server": "bleuart",
                  "tcp.client": "easysocket", "tcp.server": "easysocket",
                  "udp.client": "easysocket", "udp.server": "easysocket","power":"M5"}.get(stem, stem)
        found = []
        class_owner=None
        class_indent=-1
        currentmodule_explicit=False
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            module_match=re.match(r"\s*\.\. (?:py:)?(currentmodule|module)::\s*(\S+)",line)
            if module_match:
                directive_module,value=module_match.groups()
                if directive_module=="currentmodule":module=value;currentmodule_explicit=True
                elif not currentmodule_explicit:module=value
            match = re.match(r"\s*\.\. (?:py:)?(?:auto)?(class|method|function|data|attribute|classmethod|staticmethod)::\s*(.+)", line)
            if not match:
                continue
            directive, signature = match.groups()
            signatures = [signature]
            for continuation in lines[index + 1:]:
                text = continuation.strip()
                if not text or text.startswith(":"):
                    break
                if re.match(r"(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:\(|$)", text) and ("(" in text or directive == "data"):
                    signatures.append(text)
                else:
                    break
            for signature in signatures:
                name = signature.split("(", 1)[0].split(" ->", 1)[0].strip()
                if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", name):
                    continue
                indent=len(line)-len(line.lstrip())
                qualified=(name.startswith((module+".","software.easysocket.","modbus.modbus.")) or
                           ("."in name and name.split(".")[0]in LIBRARIES|EXTERNAL|{"hardware","M5","network","time","audio","camera","image","dl","code_scanner"}))
                if directive!="class" and class_owner and indent>class_indent and "." not in name:
                    api=class_owner+"."+name
                else:
                    api = (name if name.startswith(category + ".") else category + "." + name) if external else (
                        name if qualified else module + "." + name)
                if directive=="class":class_owner,class_indent=api,indent
                kind = "constructor" if directive == "class" else "constant" if directive == "data" else "property" if directive == "attribute" else "method"
                entry_scope="shared-runtime-hardware"if api.startswith(("hardware.","M5."))else scope
                add(api, signature, kind, relative, index + 1, entry_scope,
                    "CONTROLLER_PEER_OR_FILE" if not external else "SELECTED_ACCESSORY_DRIVER_AND_CONTROLLER")
                found.append(api)
        documents.append({"path": relative, "scope": scope, "api_count": len(set(found)),
                          "parser_status": "PARSED" if found else "REVIEWED_NO_INDEPENDENT_DECLARATIONS",
                          "audit":audit_document(path,root,found)})

    for path in sorted((root / "m5stack/libs").rglob("*.py")):
        relative_lib = path.relative_to(root / "m5stack/libs")
        top = relative_lib.parts[0].removesuffix(".py")
        if top not in LIBRARIES | EXTERNAL:
            continue
        if any(part in {"test", "tests", "example", "examples"} for part in relative_lib.parts) or path.stem.startswith("test_"):
            continue
        relative = reference(path)
        module = ".".join(relative_lib.with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module[:-9]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                add(module + "." + node.name, node.name + "(" + ast.unparse(node.args) + ")", "function",
                    relative, node.lineno, "optional-accessory" if top in EXTERNAL else "system-communication", "BEHAVIORAL_ORACLE")
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                owner = module + "." + node.name
                add(owner, node.name + "(...)", "constructor", relative, node.lineno,
                    "optional-accessory" if top in EXTERNAL else "system-communication", "BEHAVIORAL_ORACLE")
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and not member.name.startswith("_"):
                        kind = "property" if any(isinstance(x, ast.Name) and x.id == "property" for x in member.decorator_list) else "method"
                        add(owner + "." + member.name, member.name + "(" + ast.unparse(member.args) + ")", kind,
                            relative, member.lineno, "optional-accessory" if top in EXTERNAL else "system-communication", "BEHAVIORAL_ORACLE")
                    elif isinstance(member,ast.ClassDef) and not member.name.startswith("_"):
                        nested_owner=owner+"."+member.name
                        add(nested_owner,member.name+"(...)","constructor",relative,member.lineno,
                            "optional-accessory" if top in EXTERNAL else "system-communication","BEHAVIORAL_ORACLE")
                        for method in member.body:
                            if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                                add(nested_owner+"."+method.name,method.name+"("+ast.unparse(method.args)+")","method",relative,method.lineno,
                                    "optional-accessory" if top in EXTERNAL else "system-communication","BEHAVIORAL_ORACLE")
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    return {"schema_version": 2, "scope": "system-communication-and-optional-accessory-candidate-inventory",
        "source_commit": commit, "firmware_binding": "UNPROVEN_SOURCE_CANDIDATE_COMPARE_GUEST_EXPORTS",
        "devices": ["cores3", "cardputer-adv"], "sources": sources, "documents": documents,
        "source_declared_import_aliases":import_aliases,
        "known_inventory_gaps": ["Native C exports must be merged from both actual stock guests.",
            "Inherited and lazy/dynamic members require runtime comparison.",
            "Overview/placeholder/workflow pages are explicitly audited and do not grant functional PASS."],
        "entries": [entries[key] for key in sorted(entries)]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uiflow", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("inventory_system.source.json"))
    args = parser.parse_args()
    result = build(args.uiflow)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(result["entries"]), "documents": len(result["documents"]),
                      "unparsed_documents": sum(row["api_count"] == 0 for row in result["documents"])}))
