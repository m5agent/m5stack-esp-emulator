"""Actual public re-export and UART factory boundaries; no peer substitution."""
import json,machine
import usb.device.hid


def check(api,action,verify,oracle,status="PASS"):
    try:
        value=action()
        print("SYSTEM_API "+json.dumps({"api":api,"status":status if verify(value)else"FAIL","value":value,"oracle":oracle}))
    except Exception as error:
        print("SYSTEM_API "+json.dumps({"api":api,"status":"ERROR","error":repr(error),"oracle":oracle}))


check("usb.device.hid.split_bmRequestType",lambda:list(usb.device.hid.split_bmRequestType(0xa1)),lambda value:value==[1,1,1],"actual HID public helper returns normalized recipient/type/direction fields for independent bmRequestType 0xa1")
if RUN_RTU_FACTORIES:
    import modbus
    master=modbus.ModbusRTUMaster(uart_no=1,tx_pin=2,rx_pin=1,baudrate=9600)
    check("modbus.ModbusRTUMaster",lambda:isinstance(master.uart,machine.UART),lambda value:value,"original factory returned its native UART-backed master; selected Cardputer profile admits no RS485 Unit peer, so constructor observation does not establish RTU wire behavior","STATE_PASS")
    master.uart.deinit()
    uart=machine.UART(1,baudrate=9600,tx=2,rx=1,timeout=10)
    slave=modbus.ModbusRTUSlave(uart,device_address=1)
    check("modbus.ModbusRTUSlave",lambda:slave.uart is uart,lambda value:value,"original factory retains exact supplied native UART; selected Cardputer profile admits no RS485 Unit peer, so constructor observation does not establish RTU wire behavior","STATE_PASS")
    slave.stop();uart.deinit()
print("PROTOCOL_FACTORIES_DONE")
