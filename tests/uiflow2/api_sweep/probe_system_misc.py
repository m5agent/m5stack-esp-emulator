"""Stock system configuration/diagnostic boundaries, without RF claims."""
import os,json,network,gc
from umqtt.simple import MQTTException


def check(api,action,verify,oracle,status="STATE_PASS"):
    try:
        value=action();passed=verify(value)
        print("SYSTEM_API "+json.dumps({"api":api,"status":status if passed else"FAIL","value":value,"oracle":oracle}))
    except Exception as error:
        print("SYSTEM_API "+json.dumps({"api":api,"status":"ERROR","error":repr(error),"oracle":oracle}))


station=network.WLAN(network.STA_IF);station.active(True)
def country():
    old=network.country();network.country("US");observed=network.country();network.country(old);return observed
check("network.country",country,lambda value:value=="US","native regulatory-code readback; channel/range/RF behavior is not inferred")
def hostname():
    old=network.hostname();network.hostname("m5-api-fixture");observed=network.hostname();network.hostname(old);return observed
check("network.hostname",hostname,lambda value:value=="m5-api-fixture","native hostname setter/getter; a DHCP hostname option is a separate packet oracle")
def ipconfig():
    old=network.ipconfig("dns");network.ipconfig(dns="192.0.2.53");observed=network.ipconfig("dns");network.ipconfig(dns=old);return observed
check("network.ipconfig",ipconfig,lambda value:value=="192.0.2.53","native global DNS readback uses a documentation-only address, with original state restored")
check("network.phy_mode",network.phy_mode,lambda value:value is None,"official ports/esp32/network_common.c esp_phy_mode is an unconditional None compatibility stub; it provides no PHY operation","UNSUPPORTED_FIRMWARE")
check("os.dupterm_notify",lambda:os.dupterm_notify(None),lambda value:value is None,"native notification function accepts the documented IRQ callback argument; positive UART RX wakeup remains separate")
def exception_flow():
    try:raise MQTTException(5)
    except MQTTException as error:return error.args[0]
check("umqtt.simple.MQTTException",exception_flow,lambda value:value==5,"public exception preserves exact protocol error code through native raise/catch","PASS")
try:
    import audio
    check("audio.verno",audio.verno,lambda value:isinstance(value,str)and bool(value),"native ADF version metadata is observable; no playback claim")
    def memory():
        values=audio.mem_info()
        return "mem_total"in values and all(type(value)==int and value>0 for value in values.values())
    check("audio.mem_info",memory,lambda value:value,"native ADF heap diagnostic fields are positive integers; allocator accuracy needs an independent allocation oracle")
except ImportError as error:
    print("SYSTEM_EXPORT "+json.dumps({"path":"audio","status":"ABSENT","error":repr(error)}))
print("SYSTEM_MISC_DONE")
