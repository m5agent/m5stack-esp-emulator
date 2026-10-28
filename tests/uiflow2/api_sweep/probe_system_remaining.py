"""Finite public helper, inherited implementation and device-boundary probes."""
import json,time,machine,network


def check(api,action,verify,oracle,status="PASS"):
    try:
        value=action()
        print("SYSTEM_API "+json.dumps({"api":api,"status":status if verify(value)else"FAIL","value":value,"oracle":oracle}))
    except Exception as error:
        print("SYSTEM_API "+json.dumps({"api":api,"status":"ERROR","error":repr(error),"oracle":oracle}))


import bluetooth
for module_name in ("bleuart.ble_advertising","m5ble.m5ble"):
    module=__import__(module_name,None,None,["*"])
    check(module_name+".const",lambda:module.const(73),lambda value:value==73,"actual exported imported const function preserves independent integer golden value")
    if hasattr(module,"schedule"):
        events=[];module.schedule(lambda value:events.append(value),73)
        deadline=time.ticks_add(time.ticks_ms(),1000)
        while not events and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(5)
        check(module_name+".schedule",lambda:events,lambda value:value==[73],"exported native scheduler dispatches exact callback argument")
    payload=bytes.fromhex("02010603094d3503030d1803198000")
    check(module_name+".advertising_payload",lambda:bytes(module.advertising_payload(name="M5",services=[bluetooth.UUID(0x180d)],appearance=128)).hex(),lambda value:value==payload.hex(),"independent Bluetooth AD flags/name/16-bit UUID/appearance byte vector")
    check(module_name+".decode_field",lambda:[bytes(value).decode()for value in module.decode_field(payload,9)],lambda value:value==["M5"],"independent AD name field bytes")
    check(module_name+".decode_name",lambda:module.decode_name(payload),lambda value:value=="M5","independent AD name UTF-8 decode")
    for raw,expected in ((b"\x03\x03\x0d\x18",0x180d),(b"\x05\x05\x78\x56\x34\x12",0x12345678)):
        check(module_name+".decode_services",lambda raw=raw:[str(value)for value in module.decode_services(raw)],lambda value,expected=expected:value==[str(bluetooth.UUID(expected))],"independent Bluetooth AD 16/32-bit UUID golden vectors; all subcases must pass")
    if hasattr(module,"demo"):
        check(module_name+".demo",module.demo,lambda value:value is None,"bundled example runs its original advertisement/name/service prints; this is example execution only","STATE_PASS")


import modbus
from modbus.master import ModbusMaster
from modbus.slave import ModbusSlave
from modbus.frame import ModbusFrame,ModbusRTUFrame,ModbusTCPFrame
client=modbus.ModbusTCPClient("127.0.0.1",1502)
for name in dir(ModbusMaster):
    if name.startswith("_")or not callable(getattr(ModbusMaster,name)):continue
    identical=getattr(type(client),name)is getattr(ModbusMaster,name)
    print("SYSTEM_ALIAS "+json.dumps({"api":"modbus.master.ModbusMaster."+name,"target":"modbus.ModbusTCPClient."+name,"identical":identical,"scope":"inherited-implementation-via-concrete-transport"}))
uart=machine.UART(1,baudrate=9600,tx=2,rx=1,timeout=10)
server=modbus.ModbusRTUSlave(uart,device_address=1)
tcpserver=modbus.ModbusTCPServer("127.0.0.1",1502)
for name in dir(ModbusSlave):
    if name.startswith("_")or not callable(getattr(ModbusSlave,name)):continue
    identical=getattr(type(server),name)is getattr(ModbusSlave,name)
    print("SYSTEM_ALIAS "+json.dumps({"api":"modbus.slave.ModbusSlave."+name,"target":"modbus.ModbusRTUSlave."+name,"identical":identical,"scope":"inherited-implementation-via-concrete-transport"}))
    print("SYSTEM_ALIAS "+json.dumps({"api":"modbus.slave.ModbusSlave."+name,"target":"modbus.ModbusTCPServer."+name,"identical":getattr(type(tcpserver),name)is getattr(ModbusSlave,name),"scope":"inherited-implementation-via-concrete-transport"}))
request=ModbusTCPFrame(transaction_id=7,unit_id=1,func_code=3,register=0,length=2)
check("modbus.frame.ModbusRTUFrame.transform_frame",lambda:bytes(ModbusRTUFrame.transform_frame(request).get_frame()).hex(),lambda value:value=="010300000002c40b","original TCP-to-RTU transform matches independent function-03 request and CRC16 golden bytes")
check("modbus.frame.ModbusFrame.get_frame",lambda:bytes(ModbusFrame.get_frame(request)).hex(),lambda value:value=="000700000006010300000002","base implementation dispatches original concrete TCP frame encoder and matches independent MBAP golden bytes")
server.add_holding_register(32,4321)
check("modbus.ModbusRTUSlave.handle_message",lambda:bytes(server.handle_message(ModbusRTUFrame(device_addr=1,func_code=3,register=32,length=1)).get_frame()).hex(),lambda value:value=="01030210e175cc","original public handler consumes an independent request and produces exact response bytes and CRC16; frame-handler-only scope")
check("modbus.ModbusTCPServer.handle_message",lambda:bytes(tcpserver.handle_message(request).get_frame()).hex(),lambda value:value=="000700000003018302","empty context original public handler returns exact independent illegal-address exception MBAP/PDU bytes; frame-handler-only scope")
server.stop();uart.deinit()


try:
    value=network.LAN(phy_type=network.PHY_LAN8720,phy_addr=0,mdc=2,mdio=1)
    print("SYSTEM_API "+json.dumps({"api":"network.LAN","status":"OBSERVED_INCOMPLETE_EVIDENCE","oracle":"constructor returned but selected ESP32-S3 board has no integrated EMAC or attached SPI Ethernet model; Ethernet data plane not established"}))
except Exception as error:
    print("SYSTEM_API "+json.dumps({"api":"network.LAN","status":"BLOCKED_MODEL","error":repr(error),"oracle":"actual RMII constructor attempted; S3 lacks EMAC and selected board has no attached SPI Ethernet controller; this is no Ethernet functional PASS"}))
check("network.phy_mode",network.phy_mode,lambda value:value is None,"official compatibility stub returns None; no PHY mode operation is implemented","UNSUPPORTED_FIRMWARE")


uart=machine.UART(1,baudrate=115200,tx=2,rx=1,timeout=10)
print("SYSTEM_EXPORT "+json.dumps({"path":"network.PPP","members":[[name,type(getattr(network.PPP,name)).__name__,callable(getattr(network.PPP,name))]for name in dir(network.PPP)if not name.startswith("_")]}))
try:
    link=network.PPP(uart)
    print("SYSTEM_API "+json.dumps({"api":"network.PPP","status":"OBSERVED_INCOMPLETE_EVIDENCE","oracle":"actual UART stream constructor returned; independent LCP/IPCP and UDP peer execution remains required"}))
    if hasattr(link,"deinit"):link.deinit()
except TypeError as error:
    unsupported="can't create 'PPP' instances"in str(error)
    for api in ["network.PPP"]+["network.PPP."+name for name in dir(network.PPP)if not name.startswith("_")and callable(getattr(network.PPP,name))]:
        print("SYSTEM_API "+json.dumps({"api":api,"status":"UNSUPPORTED_FIRMWARE"if unsupported else"ERROR","error":repr(error),"oracle":"actual stock PPP type rejects construction with a real UART stream; an exported non-constructible type cannot establish any PPP method data plane"}))
uart.deinit()


import M5,utility
M5.begin();M5.Display.fillScreen(0)
check("utility.print_error_msg",lambda:utility.print_error_msg(ValueError("OWNED_API_SWEEP_ERROR_73")),lambda value:value is None,"original helper prints the exact exception and renders LCD error; independent retained frame/serial oracle is required","OBSERVED_PENDING_FRAME")
print("SYSTEM_REMAINING_DONE")
