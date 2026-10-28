import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[2]/"tests/uiflow2/api_sweep"
sys.path.insert(0,str(TOOLS))
from build_system_inventory import build,canonical_api
from summarize_system_results import summarize
from compact_system_results import compact,expand


class SystemInventoryTests(unittest.TestCase):
    def test_verified_protocol_aliases_keep_abstract_owners(self):
        self.assertEqual(canonical_api("easysocket.software.easysocket.tcp_server.EasyTCPServer.start"),"easysocket.EasyTCPServer.start")
        self.assertEqual(canonical_api("modbus.modbus.master.ModbusTCPClient.connect"),"modbus.ModbusTCPClient.connect")
        self.assertEqual(canonical_api("umqtt.default.MQTTClient.publish"),"umqtt.MQTTClient.publish")
        self.assertEqual(canonical_api("modbus.modbus.master.ModbusMaster.read_coils"),"modbus.master.ModbusMaster.read_coils")
        self.assertEqual(canonical_api("image.Image.find_qrcodes.result.payload"),"image.qrcode.payload")
        self.assertEqual(canonical_api("code_scanner.find_qrcodes.result.type_name"),"image.QRCode.type_name")
        self.assertEqual(canonical_api("dl.HumanFaceRecognizer.recognize.negative"),"dl.HumanFaceRecognizer.recognize")

    def test_py_domain_class_ownership_and_source_lazy_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            docs=root/"docs/source/module";docs.mkdir(parents=True)
            (docs/"fixture.rst").write_text(".. py:currentmodule:: module\n\n.. py:class:: Fixture\n\n    .. py:method:: read(value)\n")
            libs=root/"m5stack/libs/module";libs.mkdir(parents=True)
            (libs/"__init__.py").write_text('_attrs={"Fixture":"fixture"}\n')
            (libs/"fixture.py").write_text("class Fixture:\n def read(self,value):\n  return value\n")
            with patch("build_system_inventory.subprocess.check_output",return_value="a"*40):result=build(root)
            entries={row["api"]:row for row in result["entries"]}
            self.assertEqual(set(entries),{"module.Fixture","module.Fixture.read"})
            self.assertEqual(entries["module.Fixture.read"]["owner"],"module.Fixture")
            self.assertIn("module.fixture.Fixture.read",entries["module.Fixture.read"]["aliases"])
            self.assertEqual(result["documents"][0]["audit"]["status"],"PARSED_API_DIRECTIVES")

    def test_recipe_and_import_do_not_grant_functional_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            inventory=root/"inventory.json"
            inventory.write_text(json.dumps({"source_commit":"a"*40,"devices":["cores3"],"entries":[
                {"api":"requests2.get","kind":"method","scope":"system-communication","recipe_id":"protocol-peer"}]}))
            serial=root/"serial.txt"
            serial.write_text('SYSTEM_EXPORT {"path":"requests2","members":[["get","function",true]],"count":1}\n')
            result=summarize(inventory,[],[("cores3",serial)])
            row=result["entries"][0]
            self.assertEqual(row["export_status"],"PRESENT")
            self.assertEqual(row["status"],"NOT_RUN")
            self.assertFalse(row["required_evidence_met"])

    def test_runtime_noncallable_stays_in_inventory_without_functional_pass(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);inventory=root/'inventory.json';serial=root/'serial.txt'
            inventory.write_text(json.dumps({'source_commit':'a'*40,'devices':['cores3'],'entries':[]}))
            serial.write_text('SYSTEM_EXPORT {"path":"fixture","members":[["VALUE","int",false],["call","function",true]]}\n')
            rows={row['api']:row for row in summarize(inventory,[],[('cores3',serial)])['entries']}
            self.assertEqual(rows['fixture.VALUE']['status'],'INVENTORY_ONLY')
            self.assertFalse(rows['fixture.VALUE']['required_evidence_met'])
            self.assertEqual(rows['fixture.call']['status'],'NOT_RUN')

    def test_missing_runtime_identity_cannot_grant_functional_pass(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);inventory=root/'inventory.json';run=root/'run';run.mkdir()
            inventory.write_text(json.dumps({'source_commit':'a'*40,'devices':['cores3'],'entries':[{'api':'fixture.call','kind':'method','scope':'system-communication'}]}))
            (run/'report.json').write_text(json.dumps({'device_id':'cores3','status':'EXECUTED','source_sha256':'c'*64,'firmware_sha256':'d'*64,'evidence_sha256':'b'*64,'cleanup':{'runtime_pid_gone':True}}))
            (run/'serial.txt').write_text('SYSTEM_API {"api":"fixture.call","status":"PASS"}\n')
            row=summarize(inventory,[run],[])['entries'][0]
            self.assertEqual(row['status'],'OBSERVED_INCOMPLETE_EVIDENCE')
            self.assertFalse(row['required_evidence_met'])

    def test_compact_roundtrip_preserves_every_status_and_rejects_changed_inventory(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);inventory_path=root/'inventory.json'
            inventory={'source_commit':'a'*40,'devices':['cores3','cardputer-adv'],'entries':[{'api':'fixture.call','kind':'method','scope':'system-communication'}]}
            inventory_path.write_text(json.dumps(inventory))
            joined={'source_commit':'a'*40,'entries':[]}
            for device,status in [('cores3','ERROR'),('cardputer-adv','NOT_RUN')]:
                for api in ['fixture.call','fixture.VALUE']:
                    joined['entries'].append({'api':api,'device_id':device,'status':status,'blocker':'explicit failure boundary','required_evidence_met':False,'export_callable':api.endswith('call'),'export_status':'PRESENT'})
            document=compact(inventory,joined,inventory_path);restored=expand(document,inventory,inventory_path)
            self.assertEqual({(r['api'],r['device_id'],r['status'])for r in restored},{(r['api'],r['device_id'],r['status'])for r in joined['entries']})
            self.assertTrue(all(r['reason']=='explicit failure boundary'for r in restored))
            inventory_path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'inventory SHA256'):expand(document,inventory,inventory_path)

    def test_currentmodule_owns_short_module_title_and_templates_are_not_apis(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            docs=root/"docs/source/advanced";docs.mkdir(parents=True)
            (docs/"keyboard.rst").write_text(".. currentmodule:: usb.device.keyboard\n\n.. module:: keyboard\n\n.. class:: usb.device.keyboard.Keyboard()\n\n.. method:: Keyboard.send_keys()\n")
            contribute=root/"docs/source/contribute";contribute.mkdir()
            (contribute/"template.rst").write_text(".. class:: Fictitious()\n")
            (root/"m5stack/libs").mkdir(parents=True)
            with patch("build_system_inventory.subprocess.check_output",return_value="a"*40):inventory=build(root)
            self.assertEqual({row["api"]for row in inventory["entries"]},{"usb.device.keyboard.Keyboard","usb.device.keyboard.Keyboard.send_keys"})
            self.assertEqual(inventory["documents"][1]["audit"]["status"],"REVIEWED_CONTRIBUTOR_TEMPLATE")

    def test_mixed_exports_and_negative_subcase_cannot_be_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            inventory=root/"inventory.json"
            inventory.write_text(json.dumps({"source_commit":"a"*40,"devices":["cores3"],"entries":[
                {"api":"dl.ObjectDetector.infer","kind":"method","scope":"system-communication"},
                {"api":"usb.device.keyboard.Keyboard.send_keys","kind":"method","scope":"system-communication"}]}))
            run=root/"run";run.mkdir()
            (run/"report.json").write_text(json.dumps({"device_id":"cores3","status":"EXECUTED","evidence_sha256":"b"*64,"source_sha256":"c"*64,"firmware_sha256":"d"*64,"runtime_binary_sha256":"e"*64,
                "cleanup":{"runtime_pid_gone":True}}))
            (run/"serial.txt").write_text(
                'DL_EXPORT {"path":"dl.ObjectDetector","members":["infer"]}\n'
                'DL_API {"api":"dl.ObjectDetector.infer.negative","status":"FAIL"}\n'
                'DL_API {"api":"dl.ObjectDetector.infer","status":"PASS"}\n'
                'USB_API {"api":"usb.device.keyboard.Keyboard.send_keys","status":"BLOCKED_MODEL","reason":"no host endpoint"}\n')
            rows={row["api"]:row for row in summarize(inventory,[run],[])["entries"]}
            self.assertEqual(rows["dl.ObjectDetector.infer"]["export_status"],"PRESENT")
            self.assertEqual(rows["dl.ObjectDetector.infer"]["status"],"FAIL")
            self.assertFalse(rows["dl.ObjectDetector.infer"]["required_evidence_met"])
            self.assertEqual(rows["usb.device.keyboard.Keyboard.send_keys"]["blocker"],"no host endpoint")

    def test_hci_firmware_lane_cannot_change_stock_result_or_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            inventory=root/"inventory.json"
            inventory.write_text(json.dumps({"source_commit":"a"*40,"devices":["cores3"],"entries":[
                {"api":"bleuart.BLEUARTServer.write","kind":"method","scope":"system-communication"}]}))
            run=root/"run";run.mkdir()
            (run/"report.json").write_text(json.dumps({"device_id":"cores3","status":"EXECUTED","firmware_lane":"hci-offload-test-firmware"}))
            (run/"serial.txt").write_text('SYSTEM_EXPORT {"path":"fixture","members":[["hidden","function",true]]}\n')
            (run/"protocol-results.json").write_text(json.dumps({"firmware_lane":"hci-offload-test-firmware","cases":[
                {"api":"bleuart.BLEUARTServer.write","status":"PASS","required_evidence_met":True}]}))
            result=summarize(inventory,[run],[])
            self.assertEqual(len(result["entries"]),1)
            self.assertEqual(result["entries"][0]["status"],"NOT_RUN")
            self.assertEqual(len(result["diagnostic_lanes_excluded_from_stock"]),1)

    def test_inherited_identity_keeps_concrete_transport_scope(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);inventory=root/"inventory.json"
            inventory.write_text(json.dumps({"source_commit":"a"*40,"devices":["cores3"],"entries":[
                {"api":"modbus.master.ModbusMaster.read_coils","kind":"method","scope":"system-communication"},
                {"api":"modbus.ModbusTCPClient.read_coils","kind":"method","scope":"system-communication"}]}))
            run=root/"run";run.mkdir()
            (run/"report.json").write_text(json.dumps({"device_id":"cores3","status":"EXECUTED","evidence_sha256":"b"*64,"source_sha256":"c"*64,"firmware_sha256":"d"*64,"runtime_binary_sha256":"e"*64,"cleanup":{"runtime_pid_gone":True}}))
            (run/"serial.txt").write_text(
                'SYSTEM_ALIAS {"api":"modbus.master.ModbusMaster.read_coils","target":"modbus.ModbusTCPClient.read_coils","identical":true,"scope":"inherited-implementation-via-concrete-transport"}\n'
                'SYSTEM_API {"api":"modbus.ModbusTCPClient.read_coils","status":"PASS"}\n')
            rows={row["api"]:row for row in summarize(inventory,[run],[])["entries"]}
            inherited=rows["modbus.master.ModbusMaster.read_coils"]
            self.assertEqual(inherited["status"],"INHERITED_IMPLEMENTATION_PASS")
            self.assertEqual(inherited["implementation_target"],"modbus.ModbusTCPClient.read_coils")
            self.assertTrue(inherited["required_evidence_met"])


if __name__=="__main__":unittest.main()
