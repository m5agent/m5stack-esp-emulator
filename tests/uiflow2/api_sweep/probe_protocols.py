#!/usr/bin/env python3
"""Build behavioral protocol recipes for execution in the actual UIFlow guest.

Host peers supply bytes over ordinary sockets. These recipes never replace a
guest firmware driver, native API or emulated controller with host return values.
"""
from __future__ import annotations

import argparse


COMMON = '''import json,time,network,socket
def emit(api,status,value=None,oracle=None,error=None):
 row={"api":api,"status":status,"value":value,"oracle":oracle}
 if error is not None:row["error"]=error
 print("PROTOCOL_API "+json.dumps(row))
def check(api,action,verify,oracle):
 print("PROTOCOL_CALL_BEGIN "+api)
 try:
  value=action()
  emit(api,"PASS" if verify(value) else "FAIL",value,oracle)
  return value
 except Exception as error:
  emit(api,"ERROR",oracle=oracle,error=repr(error))
def require(value,message):
 if not value:raise RuntimeError(message)
def connect_wifi():
 global wlan
 wlan=network.WLAN(network.STA_IF)
 wlan.active(True)
 scan=wlan.scan()
 require(any(row[0]==b"myssid" for row in scan),"fixture AP absent")
 wlan.connect("myssid")
 for _ in range(160):
  if wlan.isconnected() and wlan.status()==1010:break
  time.sleep_ms(250)
 else:raise RuntimeError("guest DHCP timed out")
 print("PROTOCOL_NETWORK_READY")
 return wlan
'''


HTTP = '''import requests2,io
base="http://10.0.2.2:"+str(CONFIG["http"])
def response(method):
 r=getattr(requests2,method.lower())(base+"/echo",headers={"X-Guest-Method":method},timeout=5)
 body=r.content
 require(r.status_code==200,"HTTP status")
 require(r.headers.get("X-Protocol-Fixture")=="yes","HTTP fixture header")
 if method!="HEAD":require(json.loads(body)["method"]==method,"method not delivered to peer")
 else:require(body==b"","HEAD has a body")
 r.close()
 return method
for method in ("GET","HEAD","POST","PUT","PATCH","DELETE"):
 check("requests2."+method.lower(),lambda method=method:response(method),lambda value:value==method,"controlled peer received actual HTTP method and returned matching JSON")
def request_json():
 r=requests2.request("POST",base+"/echo",json={"number":42,"text":"fixture"},timeout=5)
 value=r.json()
 require(json.loads(value["body"])=={"number":42,"text":"fixture"},"JSON upload differs")
 require(r.status_code==200,"JSON status")
 r.close()
 return value["method"]
check("requests2.request",request_json,lambda value:value=="POST","actual request JSON bytes parsed by controlled peer")
r=requests2.get(base+"/echo",timeout=5)
check("requests2.Response",lambda:type(r).__name__,lambda value:value=="Response","instance created from actual socket HTTP response")
check("requests2.Response.status_code",lambda:r.status_code,lambda value:value==200,"wire HTTP status line")
check("requests2.Response.headers",lambda:r.headers.get("X-Protocol-Fixture"),lambda value:value=="yes","actual peer response header")
expected=r.content
check("requests2.Response.content",lambda:len(r.content),lambda value:value==len(expected) and json.loads(expected)["method"]=="GET","actual body bytes cached after socket read")
check("requests2.Response.text",lambda:r.text,lambda value:value.encode()==expected,"UTF8 decode of actual HTTP body")
check("requests2.Response.json",lambda:r.json()["method"],lambda value:value=="GET","JSON decode of actual HTTP body")
r.close()
check("requests2.Response.close",lambda:r.raw is None,lambda value:value,"socket closed and next request remains usable")
def form_roundtrip():
 query={"plain":"ok","space":"a b","reserved":"a&b=c","utf8":"中文"}
 encoded=requests2.urlencode(query)
 r=requests2.post(base+"/form",data=encoded,headers={"Content-Type":"application/x-www-form-urlencoded"},timeout=5)
 decoded=r.json()["form"]
 r.close()
 return decoded==query
check("requests2.urlencode",form_roundtrip,lambda value:value,"reserved and UTF8 form fields roundtrip through standard peer form decoder")
def file_upload():
 r=requests2.post(base+"/echo",data=io.BytesIO(b"file-stream-bytes"),timeout=5)
 value=r.json()["body"]
 r.close()
 return value
check("requests2.request.data_file",file_upload,lambda value:value=="file-stream-bytes","official file-object upload path sends complete bytes to peer")
'''


SOCKETS = '''address=("10.0.2.2",CONFIG["tcp"])
check("socket.getaddrinfo",lambda:socket.getaddrinfo(address[0],address[1],0,socket.SOCK_STREAM)[0][-1][1],lambda value:value==address[1],"numeric fixture address resolved with requested port")
sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect(address)
check("socket.socket",lambda:type(sock).__name__,lambda value:isinstance(value,str),"real TCP endpoint allocated and connected")
check("socket.socket.connect",lambda:list(sock.getpeername()),lambda value:value[0]==address[0] and value[1]==address[1],"peer address on established actual TCP connection")
check("socket.socket.getpeername",lambda:sock.getpeername()[1],lambda value:value==address[1],"established peer TCP port")
check("socket.socket.getsockname",lambda:sock.getsockname()[1],lambda value:value>0,"allocated guest local TCP port")
check("socket.socket.fileno",sock.fileno,lambda value:type(value)==int and value>=0,"live underlying socket descriptor")
def exchange_send():
 sent=sock.send(b"SEND\\n")
 return [sent,sock.recv(5).decode()]
check("socket.socket.send",exchange_send,lambda value:value==[5,"SEND\\n"],"actual TCP echo bytes")
def exchange_sendall():
 sock.sendall(b"ALL\\n")
 return sock.read(4).decode()
check("socket.socket.sendall",exchange_sendall,lambda value:value=="ALL\\n","all TCP payload bytes delivered and read")
def exchange_write():
 sent=sock.write(b"WRITE\\n")
 return [sent,sock.readline().decode()]
check("socket.socket.write",exchange_write,lambda value:value==[6,"WRITE\\n"],"stream write bytes and actual echoed line")
def exchange_readinto():
 sock.sendall(b"INTO\\n")
 buf=bytearray(5)
 count=sock.readinto(buf)
 return [count,buf.decode()]
check("socket.socket.readinto",exchange_readinto,lambda value:value==[5,"INTO\\n"],"peer bytes written into caller buffer")
sock.sendall(b"READ\\n")
check("socket.socket.read",lambda:sock.read(5).decode(),lambda value:value=="READ\\n","stream read of actual peer bytes")
sock.sendall(b"RECV\\n")
check("socket.socket.recv",lambda:sock.recv(5).decode(),lambda value:value=="RECV\\n","socket receive of actual peer bytes")
sock.sendall(b"LINE\\n")
check("socket.socket.readline",lambda:sock.readline().decode(),lambda value:value=="LINE\\n","actual TCP newline boundary")
check("socket.socket.setsockopt",lambda:sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1),lambda value:value is None,"set option on live socket followed by successful data exchange")
sock.setblocking(False)
def would_block():
 try:
  value=sock.recv(1)
  return value is None
 except OSError as error:return error.args[0] in (11,35,110,116,119)
check("socket.socket.setblocking",would_block,lambda value:value,"empty live nonblocking socket does not block")
sock.settimeout(5)
sock.sendall(b"TIMEOUT\\n")
check("socket.socket.settimeout",lambda:sock.recv(8).decode(),lambda value:value=="TIMEOUT\\n","socket restored to timed I/O and receives actual bytes")
stream=sock.makefile("rwb",0)
stream.write(b"MAKEFILE\\n")
check("socket.socket.makefile",lambda:stream.readline().decode(),lambda value:value=="MAKEFILE\\n","file facade reads actual peer TCP bytes")
stream.close()
sock.close()
def closed():
 try:sock.send(b"x");return False
 except OSError:return True
check("socket.socket.close",closed,lambda value:value,"closed endpoint rejects new payload")
udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
udp.settimeout(5)
uaddress=("10.0.2.2",CONFIG["udp"])
check("socket.socket.sendto",lambda:udp.sendto(b"UDP-FIXTURE",uaddress),lambda value:value==11,"actual UDP datagram sent to controlled peer")
check("socket.socket.recvfrom",lambda:udp.recvfrom(128)[0].decode(),lambda value:value=="UDP-FIXTURE","actual echoed UDP datagram")
udp.close()
listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
listener.bind(("127.0.0.1",18451));listener.listen(1);listener.settimeout(5)
peer=socket.socket();peer.settimeout(5);peer.connect(("127.0.0.1",18451))
accepted,remote=listener.accept();accepted.settimeout(5)
peer.sendall(b"ACCEPTED");require(accepted.recv(8)==b"ACCEPTED","accepted TCP bytes absent")
for api in ("socket.socket.bind","socket.socket.listen","socket.socket.accept"):
 emit(api,"PASS",True,"independent guest loopback sockets establish accepted stream and transfer exact bytes")
accepted.close();peer.close();listener.close()
'''


EASY = '''from easysocket import EasyTCPClient,EasyTCPServer,EasyUDPClient,EasyUDPServer
def spin(pump,condition):
 deadline=time.ticks_add(time.ticks_ms(),5000)
 while time.ticks_diff(deadline,time.ticks_ms())>0:
  pump()
  time.sleep_ms(5)
  if condition():return True
 return False
events=[]
c=EasyTCPClient("10.0.2.2",CONFIG["tcp"])
c.on_connect(lambda client:events.append("connect"))
c.on_data_received(lambda args:events.append(args[-1]))
c.on_disconnect(lambda client:events.append("disconnect"))
require(spin(lambda:c.check_event(0),lambda:"connect" in events),"TCP connect callback absent")
for api in ("easysocket.EasyTCPClient","easysocket.EasyTCPClient.connect","easysocket.EasyTCPClient.on_connect"):
 emit(api,"PASS",True,"actual controlled peer TCP connection and scheduled callback")
c.send(b"EASY-SEND\\n")
require(spin(lambda:c.check_event(0),lambda:b"EASY-SEND\\n" in events),"TCP receive callback absent")
for api in ("easysocket.EasyTCPClient.send","easysocket.EasyTCPClient.check_event","easysocket.EasyTCPClient.on_data_received"):
 emit(api,"PASS",True,"actual TCP echo delivered through scheduled data callback")
check("easysocket.EasyTCPClient.getpeername",lambda:c.getpeername()[1],lambda value:value==CONFIG["tcp"],"connected controlled peer port")
check("easysocket.EasyTCPClient.getsockname",lambda:c.getsockname()[1],lambda value:value>0,"allocated guest TCP port")
c.settimeout(5)
c.sendall(b"EASY-ALL\\n")
check("easysocket.EasyTCPClient.recv",lambda:c.recv(9).decode(),lambda value:value=="EASY-ALL\\n","direct receive of actual echoed sendall payload")
emit("easysocket.EasyTCPClient.sendall","PASS",True,"all bytes read from controlled echo peer")
emit("easysocket.EasyTCPClient.settimeout","PASS",True,"configured timeout then successful actual receive")
c.setblocking(False)
c.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
c.send(b"CLOSE\\n")
require(spin(lambda:c.check_event(0),lambda:"disconnect" in events),"peer EOF did not dispatch disconnect callback")
emit("easysocket.EasyTCPClient.on_disconnect","PASS",True,"controlled peer actually closes TCP stream")
c.close();c.connect()
require(spin(lambda:c.check_event(0),lambda:events.count("connect")==2),"same object reconnection absent")
c.send(b"RECONNECTED\\n")
require(spin(lambda:c.check_event(0),lambda:b"RECONNECTED\\n" in events),"reconnected data plane absent")
for api in ("easysocket.EasyTCPClient.close","easysocket.EasyTCPClient.setblocking","easysocket.EasyTCPClient.setsockopt"):
 emit(api,"PASS",True,"configured nonblocking socket survives close/reconnect and actual echo")
c.close()
uevents=[]
u=EasyUDPClient("10.0.2.2",CONFIG["udp"])
u.on_data_received(lambda args:uevents.append(args[-1]))
u.send(b"EASY-UDP")
require(spin(lambda:u.check_event(0),lambda:b"EASY-UDP" in uevents),"UDP callback bytes absent")
for api in ("easysocket.EasyUDPClient","easysocket.EasyUDPClient.connect","easysocket.EasyUDPClient.send","easysocket.EasyUDPClient.on_data_received","easysocket.EasyUDPClient.check_event"):
 emit(api,"PASS",True,"actual controlled UDP echo reaches scheduled callback")
check("easysocket.EasyUDPClient.getpeername",lambda:u.getpeername()[1],lambda value:value==CONFIG["udp"],"connected datagram peer port")
check("easysocket.EasyUDPClient.getsockname",lambda:u.getsockname()[1],lambda value:value>0,"allocated datagram local port")
u.close();u.connect()
u.sendto(b"UDP-AGAIN",("10.0.2.2",CONFIG["udp"]))
require(spin(lambda:u.check_event(0),lambda:b"UDP-AGAIN" in uevents),"UDP reopen/sendto absent")
emit("easysocket.EasyUDPClient.sendto","PASS",True,"actual echoed datagram after close/reconnect")
u.close()
emit("easysocket.EasyUDPClient.close","PASS",True,"datagram endpoint can be closed then reopened")
u.connect();u.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
def udp_direct(method,payload):
 import select
 u.send(payload)
 poll=select.poll();poll.register(u._client_sock,select.POLLIN)
 require(bool(poll.poll(5000)),"direct UDP bytes absent")
 result=getattr(u,method)(64)
 return (result[0] if method=="recvfrom" else result).decode()
check("easysocket.EasyUDPClient.recv",lambda:udp_direct("recv",b"DIRECT-RECV"),lambda value:value=="DIRECT-RECV","actual peer UDP bytes read directly")
check("easysocket.EasyUDPClient.recvfrom",lambda:udp_direct("recvfrom",b"DIRECT-FROM"),lambda value:value=="DIRECT-FROM","actual peer UDP datagram and sender address")
emit("easysocket.EasyUDPClient.setsockopt","PASS",True,"live UDP option followed by exact peer exchange")
u.close()
us=EasyUDPServer("127.0.0.1",18452)
us.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
us_events=[]
us.on_data_received(lambda args:us_events.append(args))
up=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);up.settimeout(5)
up.sendto(b"SERVER-UDP",("127.0.0.1",18452))
require(spin(lambda:us.check_event(0),lambda:bool(us_events)),"UDP server callback absent")
require(us_events[0][-1]==b"SERVER-UDP","UDP server payload differs")
for api in ("easysocket.EasyUDPServer","easysocket.EasyUDPServer.start","easysocket.EasyUDPServer.check_event","easysocket.EasyUDPServer.on_data_received"):
 emit(api,"PASS",True,"actual guest loopback UDP datagram reaches scheduled callback")
emit("easysocket.EasyUDPServer.setsockopt","PASS",True,"live listener option followed by received guest datagram")
us.sendto(b"SERVER-BACK",us_events[0][-2])
check("easysocket.EasyUDPServer.sendto",lambda:up.recvfrom(64)[0].decode(),lambda value:value=="SERVER-BACK","server response read by actual datagram peer")
us.stop();us.start()
up.sendto(b"RESTART",("127.0.0.1",18452))
require(spin(lambda:us.check_event(0),lambda:len(us_events)==2),"UDP listener restart absent")
emit("easysocket.EasyUDPServer.stop","PASS",True,"stopped endpoint rebound and delivered a new datagram")
us.close();up.close()
emit("easysocket.EasyUDPServer.close","PASS",True,"real UDP listener released after restart")
server=EasyTCPServer("127.0.0.1",18453)
server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
server.settimeout(5);server.setblocking(False)
connections=[];messages=[];disconnections=[]
server.on_client_connect(lambda client:connections.append(client))
server.on_data_received(lambda args:messages.append(args))
server.on_client_disconnect(lambda client:disconnections.append(client))
peer=socket.socket();peer.settimeout(5);peer.connect(("127.0.0.1",18453))
require(spin(lambda:server.check_event(0),lambda:bool(connections)),"TCP server accept callback absent")
accepted=connections[0]
peer.sendall(b"SERVER-IN")
require(spin(lambda:server.check_event(0),lambda:bool(messages)),"TCP server data callback absent")
require(messages[0][0] is accepted and messages[0][1]==b"SERVER-IN","server callback payload differs")
for api in ("easysocket.EasyTCPServer","easysocket.EasyTCPServer.start","easysocket.EasyTCPServer.on_client_connect","easysocket.EasyTCPServer.on_data_received","easysocket.EasyTCPServer.check_event","easysocket.EasyTCPServer.setsockopt","easysocket.EasyTCPServer.setblocking","easysocket.EasyTCPServer.settimeout"):
 emit(api,"PASS",True,"real guest loopback accepted socket and exact data callback after listener configuration")
check("easysocket.EasyTCPServer.get_sessions",lambda:len(server.get_sessions()),lambda value:value==1 and server.get_sessions()[0] is accepted,"actual connected client wrapper identity")
check("easysocket.EasyTCPServer.getsockname",lambda:server.getsockname()[1],lambda value:value==18453,"bound actual listener port")
emit("easysocket.EasyTCPClientSocket","PASS",True,"wrapper obtained from real accepted connection")
check("easysocket.EasyTCPClientSocket.getsockname",lambda:accepted.getsockname()[1],lambda value:value==18453,"accepted endpoint local port")
check("easysocket.EasyTCPClientSocket.getpeername",lambda:accepted.getpeername()[1],lambda value:value==peer.getsockname()[1],"accepted endpoint matches independent peer")
accepted.settimeout(5);peer.sendall(b"WRAPPER-RECV")
check("easysocket.EasyTCPClientSocket.recv",lambda:accepted.recv(32).decode(),lambda value:value=="WRAPPER-RECV","direct accepted-wrapper read of actual peer bytes")
emit("easysocket.EasyTCPClientSocket.settimeout","PASS",True,"timed accepted-wrapper read delivered peer data")
accepted.send(b"WRAPPER-SEND")
check("easysocket.EasyTCPClientSocket.send",lambda:peer.recv(32).decode(),lambda value:value=="WRAPPER-SEND","actual accepted-wrapper send reaches independent peer")
accepted.setblocking(False);accepted.sendall(b"WRAPPER-ALL")
check("easysocket.EasyTCPClientSocket.sendall",lambda:peer.recv(32).decode(),lambda value:value=="WRAPPER-ALL","all bytes from nonblocking accepted wrapper reach peer")
emit("easysocket.EasyTCPClientSocket.setblocking","PASS",True,"nonblocking accepted wrapper delivers exact sendall bytes")
peer.close()
require(spin(lambda:server.check_event(0),lambda:bool(disconnections)),"TCP server disconnect callback absent")
require(not server.get_sessions(),"server retains closed client")
emit("easysocket.EasyTCPServer.on_client_disconnect","PASS",True,"peer EOF removes live client and dispatches callback")
server.stop();server.start()
peer=socket.socket();peer.settimeout(5);peer.connect(("127.0.0.1",18453))
require(spin(lambda:server.check_event(0),lambda:len(connections)==2),"TCP server restart failed")
emit("easysocket.EasyTCPServer.stop","PASS",True,"listener released then rebound and accepted new connection")
connections[-1].close()
check("easysocket.EasyTCPClientSocket.close",lambda:peer.recv(1),lambda value:value==b"","wrapper close produces real peer EOF")
peer.close();server.close()
emit("easysocket.EasyTCPServer.close","PASS",True,"listener and accepted endpoints released after restart")
try:
 server=EasyTCPServer("127.0.0.1",18454)
 value=server.getpeername()
 emit("easysocket.EasyTCPServer.getpeername","NOT_APPLICABLE_LISTENER",value,"public forwarding method has no connected peer on a listening socket; no functional peer-address PASS")
except OSError as error:
 emit("easysocket.EasyTCPServer.getpeername","NOT_APPLICABLE_LISTENER",error.args[0],"listening socket cannot expose a peer; boundary result is not functional PASS")
finally:server.close()
'''


MQTT = '''import umqtt,umqtt.simple,umqtt.robust
for module,prefix in ((umqtt.simple,"umqtt.simple.MQTTClient"),(umqtt.robust,"umqtt.robust.MQTTClient"),(umqtt,"umqtt.MQTTClient")):
 events=[]
 client=module.MQTTClient(prefix,"10.0.2.2",port=CONFIG["mqtt"],keepalive=30)
 client.set_last_will(b"fixture/will",b"owned-offline",qos=1,retain=True)
 if module is umqtt:client.set_callback(client._callback)
 else:client.set_callback(lambda topic,message:events.append([topic,message]))
 require(client.connect(timeout=5)==0,"unexpected CONNACK session flag")
 emit(prefix,"PASS",True,"original frozen constructor establishes actual MQTT session")
 emit(prefix+".connect","PASS",True,"actual MQTT CONNECT/CONNACK wire exchange")
 emit(prefix+".set_last_will","PASS",True,"will topic and bytes included in actual CONNECT packet; peer evidence records fields")
 check(prefix+".isconnected",client.isconnected,lambda value:value,"actual PINGREQ write on connected broker socket")
 client.wait_msg()
 client.ping();client.wait_msg()
 emit(prefix+".ping","PASS",True,"actual PINGREQ/PINGRESP processed by original wait_msg")
 topic=b"fixture/"+prefix.encode()
 if module is umqtt:client.subscribe(topic,lambda data:events.append(list(data)))
 else:client.subscribe(topic)
 client.publish(topic,b"qos-zero",qos=0)
 client.wait_msg();time.sleep_ms(50)
 require(events==[[topic,b"qos-zero"]],"QoS0 callback differs")
 for method in ("subscribe","publish","wait_msg","set_callback"):
  emit(prefix+"."+method,"PASS",True,"SUBACK plus real QoS0 publication delivered through original callback")
 client.publish(topic,b"qos-one",qos=1)
 deadline=time.ticks_add(time.ticks_ms(),5000)
 while len(events)<2 and time.ticks_diff(deadline,time.ticks_ms())>0:
  client.check_msg();time.sleep_ms(10)
 require(events[-1]==[topic,b"qos-one"],"QoS1 callback differs")
 emit(prefix+".check_msg","PASS",True,"actual QoS1 PUBACK and peer publication processed without blocking foreground loop")
 client.unsubscribe(topic)
 client.publish(topic,b"unsubscribed")
 time.sleep_ms(100);client.check_msg();time.sleep_ms(10)
 require(len(events)==2,"unsubscribe still delivers messages")
 emit(prefix+".unsubscribe","PASS",True,"UNSUBACK followed by publish has no subscription callback")
 client.disconnect()
 if module is not umqtt.simple:
  client.reconnect()
  if module is umqtt:client.subscribe(topic,lambda data:events.append(list(data)))
  else:client.subscribe(topic)
  client.publish(topic,b"reconnected");client.wait_msg();time.sleep_ms(50)
  require(events[-1]==[topic,b"reconnected"],"reconnected delivery absent")
  emit(prefix+".reconnect","PASS",True,"second real CONNECT after closed session then renewed subscription and payload")
  before=time.ticks_ms();client.delay(1);elapsed=time.ticks_diff(time.ticks_ms(),before)
  check(prefix+".delay",lambda:elapsed,lambda value:value>=1900,"original robust retry delay advances guest clock by configured two seconds")
  client.DEBUG=True;client.log(False,RuntimeError("fixture-log-marker"));client.DEBUG=False
  emit(prefix+".log","PASS",True,"original DEBUG logger emits fixture-log-marker into serial evidence")
  client.disconnect()
 try:client.sock.send(b"x");closed=False
 except OSError:closed=True
 check(prefix+".disconnect",lambda:closed,lambda value:value,"DISCONNECT wire packet and closed socket rejects further writes")
'''


NETWORK = '''
check("network.WLAN",lambda:wlan.isconnected(),lambda value:value,"actual STA instance supplied DHCP address and working protocol session")
check("network.WLAN.active",lambda:wlan.active(),lambda value:value is True,"STA activation followed by actual scan and DHCP")
check("network.WLAN.scan",lambda:any(row[0]==b"myssid" for row in wlan.scan()),lambda value:value,"emulated radio returns configured AP through actual driver")
check("network.WLAN.connect",lambda:wlan.isconnected(),lambda value:value,"connection acquires DHCP lease before application traffic")
check("network.WLAN.isconnected",wlan.isconnected,lambda value:value,"connected driver status after DHCP")
check("network.WLAN.status",wlan.status,lambda value:value==1010,"driver reports connected with IP")
original=wlan.ifconfig()
check("network.WLAN.ifconfig",lambda:list(original),lambda value:value[0].startswith("10.0.2.") and value[2]=="10.0.2.2","actual DHCP tuple from owned SLiRP peer")
wlan.ifconfig(original)
require(tuple(wlan.ifconfig())==tuple(original),"static ifconfig tuple readback differs")
def network_payload():
 peer=socket.socket();peer.settimeout(5);peer.connect(("10.0.2.2",CONFIG["tcp"]))
 peer.sendall(b"NETWORK-CONFIG");value=peer.recv(32);peer.close()
 return value==b"NETWORK-CONFIG"
require(network_payload(),"traffic failed after ifconfig setter")
emit("network.WLAN.ifconfig.set","PASS",True,"same legal address tuple readback and actual TCP payload after setter")
def config_power():
 original=wlan.config("txpower")
 wlan.config(txpower=original)
 require(network_payload(),"traffic failed after config setter")
 return [original,wlan.config("txpower")]
check("network.WLAN.config",config_power,lambda value:abs(value[0]-value[1])<=1.5,"legal transmit-power config readback allows the esp_wifi quantization step; actual subsequent TCP traffic; RF power unmeasured")
def ipconfig():
 original=wlan.ipconfig("addr4")
 wlan.ipconfig(addr4=original)
 require(network_payload(),"traffic failed after ipconfig setter")
 return list(wlan.ipconfig("addr4"))
check("network.WLAN.ipconfig",ipconfig,lambda value:bool(value) and str(value[0]).startswith("10.0.2."),"legal IPv4 configuration readback and actual subsequent TCP traffic")
def set_default():
 result=wlan.set_default()
 require(network_payload(),"default route no longer delivers TCP bytes")
 return result
check("network.WLAN.set_default",set_default,lambda value:value is True,"select STA as default route returns success and subsequent TCP connection delivers exact bytes")
wlan.disconnect()
deadline=time.ticks_add(time.ticks_ms(),5000)
while wlan.isconnected() and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
check("network.WLAN.disconnect",lambda:wlan.isconnected(),lambda value:value is False,"explicit disconnect clears driver connection state")
wlan.active(False)
check("network.WLAN.active.deactivate",lambda:wlan.active(),lambda value:value is False,"explicit deactivate clears actual interface state")
connect_wifi();require(network_payload(),"reactivated interface TCP data absent")
emit("network.WLAN.reconnect","PASS",True,"deactivation and new DHCP followed by fresh TCP data")
'''


MODBUS = '''import modbus,asyncio,struct,select
from modbus.frame import ModbusTCPFrame,ModbusRTUFrame
reads=(("read_coils",[False,True,False]),("read_discrete_inputs",[False,True,False]),("read_holding_registers",[1000,1001,1002]),("read_input_registers",[1000,1001,1002]))
writes=(("write_single_coil",True,True,"read_coils",[True]),("write_single_register",4321,4321,"read_holding_registers",[4321]),("write_multiple_coils",[True,False,True],3,"read_coils",[True,False,True]),("write_multiple_registers",[2101,2102,2103],3,"read_holding_registers",[2101,2102,2103]))
if CONFIG.get("modbus_master_source"):
 with open("/flash/candidate_modbus_master.py","w")as handle:handle.write(CONFIG["modbus_master_source"])
 _candidate_source=open("/flash/candidate_modbus_master.py").read().replace("from .frame import","from modbus.frame import")
 _candidate={"__name__":"candidate_modbus_master"}
 exec(compile(_candidate_source,"/flash/candidate_modbus_master.py","exec"),_candidate)
 TCPClient=_candidate["ModbusTCPClient"]
 print("PROTOCOL_SCOPE candidate Modbus master source lane; relative import rebased to stock modbus.frame; stock firmware failure remains unchanged")
else:TCPClient=modbus.ModbusTCPClient
client=TCPClient("10.0.2.2",CONFIG["modbus"])
client.connect();client.sock.settimeout(5)
require(client.read_holding_registers(1,0,3)==[1000,1001,1002],"initial Modbus TCP payload differs")
emit("modbus.ModbusTCPClient","PASS",True,"original frozen client exchanges real MBAP/PDU with owned peer")
emit("modbus.ModbusTCPClient.connect","PASS",True,"real TCP connection carries matching Modbus transaction ID and data")
for method,expected in reads:
 check("modbus.ModbusTCPClient."+method,lambda method=method:getattr(client,method)(1,0,3),lambda value,expected=expected:value==expected,"owned peer response values decoded from actual TCP wire")
for method,value,expected,reader,readback in writes:
 def write_verify(method=method,value=value,reader=reader,readback=readback):
  result=getattr(client,method)(1,16,value)
  require(getattr(client,reader)(1,16,len(readback))==readback,"write readback differs")
  return result
 check("modbus.ModbusTCPClient."+method,write_verify,lambda result,expected=expected:result==expected,"wire write acknowledged then independent wire read returns written values")
client.disconnect()
check("modbus.ModbusTCPClient.disconnect",lambda:client.connected,lambda value:value is False,"closed actual TCP client clears connected state")
for method,expected in reads:
 def run_async_read(method=method):
  client=TCPClient("10.0.2.2",CONFIG["modbus"]);client.connect();client.sock.settimeout(5)
  try:return asyncio.run(getattr(client,method+"_async")(1,0,3))
  finally:client.disconnect()
 check("modbus.ModbusTCPClient."+method+"_async",run_async_read,lambda result,expected=expected:result==expected,"original async method must decode actual TCP response without replacing event loop")
for method,value,expected,reader,readback in writes:
 def run_async_write(method=method,value=value,reader=reader,readback=readback):
  client=TCPClient("10.0.2.2",CONFIG["modbus"]);client.connect();client.sock.settimeout(5)
  try:
   result=asyncio.run(getattr(client,method+"_async")(1,16,value))
   require(getattr(client,reader)(1,16,len(readback))==readback,"async write readback differs")
   return result
  finally:client.disconnect()
 check("modbus.ModbusTCPClient."+method+"_async",run_async_write,lambda result,expected=expected:result==expected,"original async wire write and independent readback")
tcp=ModbusTCPFrame(transaction_id=1,unit_id=1,func_code=3,register=0,length=2)
tcp_raw=bytes(tcp.get_frame())
for api in ("modbus.frame.ModbusTCPFrame","modbus.frame.ModbusTCPFrame.get_frame"):
 check(api,lambda:tcp_raw.hex(),lambda value:value=="000100000006010300000002","fixed independent MBAP and function-03 request golden vector")
check("modbus.frame.ModbusTCPFrame.parse_frame",lambda:ModbusTCPFrame.parse_frame(tcp_raw).register,lambda value:value==0,"known TCP request vector parsed into requested register")
rtu=ModbusRTUFrame(device_addr=1,func_code=3,register=0,length=2)
rtu_raw=bytes(rtu.get_frame())
for api in ("modbus.frame.ModbusRTUFrame","modbus.frame.ModbusRTUFrame.get_frame"):
 check(api,lambda:rtu_raw.hex(),lambda value:value=="010300000002c40b","fixed independent Modbus RTU CRC16 request golden vector")
check("modbus.frame.ModbusRTUFrame.parse_frame",lambda:ModbusRTUFrame.parse_frame(rtu_raw).length,lambda value:value==2,"known RTU request vector passes CRC and parsed quantity")
server=modbus.ModbusTCPServer("127.0.0.1",18455)
print("PROTOCOL_FACTORY_EXPORT "+json.dumps({"api":"modbus.ModbusTCPServer","members":[name for name in dir(server) if not name.startswith("_")]}))
server.start()
peer=socket.socket();peer.settimeout(5);peer.connect(("127.0.0.1",18455));server.tick()
def wire_read(code,address,quantity):
 request=struct.pack(">HHHBBHH",1,0,6,1,code,address,quantity)
 peer.sendall(request);poll=select.poll();poll.register(peer,select.POLLIN)
 deadline=time.ticks_add(time.ticks_ms(),5000)
 while time.ticks_diff(deadline,time.ticks_ms())>0:
  server.tick();time.sleep_ms(5)
  if poll.poll(0):break
 else:raise RuntimeError("guest Modbus server response absent")
 response=peer.recv(128)
 require(response[:2]==b"\\x00\\x01","server transaction ID differs")
 if code in (1,2):return [bool(response[9+index//8]&(1<<(index%8))) for index in range(quantity)]
 return [int.from_bytes(response[9+index*2:11+index*2],"big") for index in range(quantity)]
for suffix,plural,code,initial,changed,multiple in (("coil","coils",1,False,True,[True,False,True]),("discrete_input","discrete_input",2,False,True,[True,False,True]),("holding_register","holding_register",3,1234,4321,[901,902,903]),("input_register","input_register",4,1234,4321,[901,902,903])):
 for index in range(3):getattr(server,"add_"+suffix)(32+index,initial)
 require(wire_read(code,32,3)==[initial]*3,"server added context not visible on wire")
 emit("modbus.ModbusTCPServer.add_"+suffix,"PASS",True,"added register context returned by real independent loopback Modbus request")
 check("modbus.ModbusTCPServer.get_"+suffix,lambda suffix=suffix:getattr(server,"get_"+suffix)(32),lambda result,initial=initial:result==initial,"context getter matches real wire read")
 getattr(server,"set_"+suffix)(32,changed)
 require(wire_read(code,32,1)==[changed],"server changed context absent on wire")
 emit("modbus.ModbusTCPServer.set_"+suffix,"PASS",True,"single context update read through real independent TCP Modbus peer")
 getattr(server,"set_multi_"+plural)(32,multiple)
 require(wire_read(code,32,3)==multiple,"server multiple context differs on wire")
 emit("modbus.ModbusTCPServer.set_multi_"+plural,"PASS",True,"multiple context update decoded from actual TCP response")
 getattr(server,"remove_"+suffix)(33)
 try:getattr(server,"get_"+suffix)(33);removed=False
 except KeyError:removed=True
 require(getattr(server,"get_"+suffix)(32)==multiple[0] and getattr(server,"get_"+suffix)(34)==multiple[2],"removal damaged neighbors")
 check("modbus.ModbusTCPServer.remove_"+suffix,lambda:removed,lambda value:value,"middle register removed while both neighboring context values remain intact")
events=[]
server.set_callback(server.READ_HOLDING_REGISTERS_EVENT,lambda args:events.append(args))
require(wire_read(3,32,1)==[901],"callback-associated wire result differs");time.sleep_ms(50)
require(events and events[0][1]==32 and events[0][2]==[901],"server scheduled callback differs")
for method in ("set_callback","tick","start"):
 emit("modbus.ModbusTCPServer."+method,"PASS",True,"real TCP request processed and matching scheduled register callback observed")
emit("modbus.ModbusTCPServer","PASS",True,"factory-created frozen server answers independent actual Modbus loopback requests")
server.stop()
peer.sendall(struct.pack(">HHHBBHH",1,0,6,1,3,32,1));server.tick()
poll=select.poll();poll.register(peer,select.POLLIN)
check("modbus.ModbusTCPServer.stop",lambda:bool(poll.poll(100)),lambda value:value is False,"stopped server tick no longer dispatches a queued Modbus request")
peer.close();server.sock.close()
'''


EZDATA = '''import ezdata,os
ezdata._server="http://10.0.2.2:"+str(CONFIG["http"])+"/ez"
print("PROTOCOL_SCOPE EzData original frozen SDK against owned HTTP fixture; external account NOT RUN")
client=ezdata.EzData("owned-fixture-token","fixture-key")
check("ezdata.EzData.set",lambda:client.set({"number":42,"text":"wire-value"}),lambda value:value=={"number":42,"text":"wire-value"},"original SDK JSON bytes stored by owned HTTP fixture")
check("ezdata.EzData.get",client.get,lambda value:value=={"number":42,"text":"wire-value"},"owned HTTP fixture returns previously stored JSON value through original SDK")
emit("ezdata.EzData","PASS",True,"frozen SDK constructor configures token/key and actual write/read wire roundtrip")
before=client.get_update_time()
require(client.set(43)==43,"second fixture write absent")
check("ezdata.EzData.has_new_data",client.has_new_data,lambda value:value is True,"fixture timestamp advances on actual second HTTP write and original SDK detects update")
check("ezdata.EzData.get_update_time",client.get_update_time,lambda value:value>before,"original SDK returns advanced fixture timestamp from actual GET")
check("ezdata.EzData.history",client.history,lambda value:value[-2:]==[{"number":42,"text":"wire-value"},43],"owned fixture historical JSON writes decoded through original SDK")
check("ezdata.get_key_list",lambda:ezdata.get_key_list("owned-fixture-token"),lambda value:value.get("fixture-key")==43,"owned HTTP key listing includes actual stored value")
path="/flash/fixture-upload.bin"
with open(path,"wb") as handle:handle.write(b"EZDATA-FILE-WIRE-012345")
upload=ezdata.EzData("owned-fixture-token","fixture-file")
def upload_file():
 result=upload.set(path,is_file=True)
 keys=ezdata.get_key_list("owned-fixture-token")
 require("fixture-file" in keys,"standard multipart parser did not receive exact requested key")
 return result
check("ezdata.EzData.set.file",upload_file,lambda value:value=="fixture-upload.bin","actual multipart upload must preserve exact key and file bytes under standard MIME parser")
check("ezdata.EzData.get.file_metadata",upload.get,lambda value:isinstance(value,str) and value.startswith("http://10.0.2.2:"),"owned HTTP metadata supplies uploaded file download URL")
upload.get_file("/flash/fixture-download.bin")
check("ezdata.EzData.get_file",lambda:open("/flash/fixture-download.bin","rb").read().decode(),lambda value:value=="EZDATA-FILE-WIRE-012345","actual HTTP file upload then download yields exact independent file bytes")
from ezdata.multi import MultiPartForm
form=MultiPartForm();form.add_field("field","value");form.add_file("file",path)
for api in ("ezdata.multi.MultiPartForm","ezdata.multi.MultiPartForm.add_field","ezdata.multi.MultiPartForm.add_file"):
 emit(api,"PASS",True,"real local file and field encoded by frozen multipart implementation")
check("ezdata.multi.MultiPartForm.content_type",form.content_type,lambda value:value=="multipart/form-data; boundary="+form.boundary,"declared boundary matches generated real multipart body")
body=form.content()
check("ezdata.multi.MultiPartForm.content",lambda:body.decode(),lambda value:"EZDATA-FILE-WIRE-012345" in value and "name=\\"field\\"" in value and value.endswith("--"+form.boundary+"--\\r\\n"),"multipart body contains exact field, original file bytes and closing boundary")
check("ezdata.multi.MultiPartForm.content_length",form.content_length,lambda value:value==len(body),"independent byte length equals produced multipart body")
check("ezdata.EzData.delete",upload.delete,lambda value:value is True,"original DELETE reaches owned fixture and removes uploaded key")
require("fixture-file" not in ezdata.get_key_list("owned-fixture-token"),"deleted key remains in fixture")
os.remove(path)
try:os.remove("/flash/fixture-download.bin")
except OSError:pass
'''


REQUESTS_CORRECTION = '''
with open("/flash/api_sweep_requests2.py","w") as handle:handle.write(CONFIG["requests_source"])
import api_sweep_requests2 as requests2
print("PROTOCOL_SCOPE candidate source lane; does not grant stock firmware PASS")
base="http://10.0.2.2:"+str(CONFIG["http"])
def form():
 fields={"plain":"ok","space":"a b","reserved":"a&b=c","utf8":"中文","plus":"+/%?","":"empty-key","tilde":"~._-"}
 encoded=requests2.urlencode(fields)
 response=requests2.post(base+"/form",data=encoded,headers={"Content-Type":"application/x-www-form-urlencoded"},timeout=5)
 result=response.json()["form"];response.close()
 return result==fields
check("candidate.requests2.urlencode",form,lambda value:value,"candidate implementation actual form HTTP bytes decode using host standard parser, including reserved UTF8 and empty key")
def unicode_body():
 response=requests2.post(base+"/echo",data="中文🚀",timeout=5)
 result=response.json()["body"];response.close()
 return result
check("candidate.requests2.request.utf8_length",unicode_body,lambda value:value=="中文🚀","Content-Length counts encoded UTF8 bytes and actual controlled peer receives complete Unicode text")
'''


BLE_NUS='''import bluetooth,M5
from bleuart import BLEUARTServer
M5.begin()
identity=CONFIG["ble_identity"]
events=[]
server=BLEUARTServer(name=identity[0])
server.irq(lambda:events.append("rx"))
deadline=time.ticks_add(time.ticks_ms(),45000)
while server.any()<len(identity[1]) and time.ticks_diff(deadline,time.ticks_ms())>0:
 M5.update();time.sleep_ms(20)
require(server.any()==len(identity[1]),"actual NUS peer write absent")
emit("bleuart.BLEUARTServer.any","PASS",server.any(),"real external Bumble GATT write populates original server receive buffer")
first=server.read(3);remainder=server.readline(max_size=len(identity[1])-3)
require(bytes(first+remainder)==identity[1].encode(),"original server receive bytes differ")
for method in ("read","readline"):
 emit("bleuart.BLEUARTServer."+method,"PASS",True,"exact real NUS payload partition read across partial read and bounded readline")
require(events==["rx"],"server IRQ did not accompany actual peer GATT write")
emit("bleuart.BLEUARTServer.irq","PASS",True,"user callback dispatched on actual GATTS_WRITE")
server.write(b"ACK:"+identity[1].encode())
time.sleep_ms(2500)
emit("bleuart.BLEUARTServer.write","OBSERVED_PENDING_PEER",True,"notification must be independently received by external Bumble central")
emit("bleuart.BLEUARTServer","OBSERVED_PENDING_PEER",True,"native constructor advertises/registers NUS and receives actual central write")
server.close();time.sleep_ms(500)
check("bleuart.BLEUARTServer.close",lambda:len(server._connections),lambda value:value==0,"real central disconnected and original server connection tracking cleared")
check("bleuart.BLEUARTServer.deinit",lambda:(server.deinit(),server._ble.active())[1],lambda value:value is False,"original native BLE interface deactivated after real exchange")
'''


M5BLE_SERVER='''import M5,bluetooth
from m5ble import M5BLE
M5.begin()
identity=CONFIG["ble_identity"]
for name in ("Device","Server","Client"):
 target=getattr(M5BLE,name)
 print("SYSTEM_EXPORT "+json.dumps({"path":"m5ble.M5BLE."+name,"count":len(dir(target)),"members":[[member,type(getattr(target,member)).__name__,callable(getattr(target,member))]for member in dir(target)if not member.startswith("_")]}))
payload=M5BLE.advertising_payload(name=b"owned-fixture",services=[bluetooth.UUID(0x180f)],appearance=128)
check("m5ble.m5ble.advertising_payload",lambda:bytes(payload).hex(),lambda value:"6f776e65642d66697874757265" in value,"independent expected device name bytes present in generated Bluetooth AD fields")
check("m5ble.m5ble.decode_name",lambda:M5BLE.decode_name(payload),lambda value:value=="owned-fixture","original AD name decoder returns known independent payload field")
check("m5ble.m5ble.decode_field",lambda:bytes(M5BLE.decode_field(payload,9)[0]).decode(),lambda value:value=="owned-fixture","raw AD type9 name field decoded")
check("m5ble.m5ble.decode_services",lambda:[str(value)for value in M5BLE.decode_services(payload)],lambda value:any("180f"in value.lower()for value in value),"known16bit service UUID decoded from actual generated AD byte fields")
device=M5BLE.Device(name=identity[0])
connected=[];received=[];disconnected=[]
device.server.clear_services()
rx_uuid="6E400002-B5A3-F393-E0A9-E50E24DCCA9E";tx_uuid="6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
rx=device.server.create_characteristic(rx_uuid,read=True,write=True)
tx=device.server.create_characteristic(tx_uuid,notify=True)
device.server.add_service("6E400001-B5A3-F393-E0A9-E50E24DCCA9E",[tx,rx])
device.server.on_connected(lambda args:connected.append(args[1]))
device.server.on_receive(lambda args:received.append(args[1]))
device.server.on_disconnected(lambda args:disconnected.append(args[1]))
device.server.start()
deadline=time.ticks_add(time.ticks_ms(),45000)
while not received and time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
require(connected and received,"m5ble actual central write absent")
client=received[0]
check("m5ble.m5ble.Server.Client.any",lambda:client.any(rx_uuid),lambda value:value==len(identity[1]),"real peer GATT write reaches original connected-client receive queue")
check("m5ble.m5ble.Server.Client.read",lambda:bytes(client.read(rx_uuid)).decode(),lambda value:value==identity[1],"exact peer write payload decoded from original per-client queue")
check("m5ble.m5ble.Server.get_clients",lambda:len(device.server.get_clients()),lambda value:value==1 and client in device.server.get_clients(),"actual connected client object retained by server")
check("m5ble.m5ble.Server.get_client",lambda:device.server.get_client(0) is client,lambda value:value,"indexed client accessor must return actual connected client")
client.write(b"ACK:"+identity[1].encode(),tx_uuid);time.sleep_ms(2500)
for api in ("m5ble.m5ble.Device","m5ble.m5ble.Server","m5ble.m5ble.Server.clear_services","m5ble.m5ble.Server.create_characteristic","m5ble.m5ble.Server.add_service","m5ble.m5ble.Server.start","m5ble.m5ble.Server.on_connected","m5ble.m5ble.Server.on_receive","m5ble.m5ble.Server.Client","m5ble.m5ble.Server.Client.write"):
 emit(api,"OBSERVED_PENDING_PEER",True,"configured original NUS server receives peer write and peer must independently verify ACK")
check("m5ble.m5ble.Device.get_mtu",device.get_mtu,lambda value:isinstance(value,int) and value>=23,"actual BLE session MTU tracked by original Device")
client.close();time.sleep_ms(300)
check("m5ble.m5ble.Server.Client.close",lambda:len(device.server.get_clients()),lambda value:value==0,"actual connected GATT peer disconnected and removed")
check("m5ble.m5ble.Server.on_disconnected",lambda:bool(disconnected),lambda value:value,"original callback delivered for actual connection teardown")
check("m5ble.m5ble.Device.deinit",lambda:(device.deinit(),device._ble.active())[1],lambda value:value is False,"original native BLE deactivated after session teardown")
'''


BLE_CLIENT='''import M5
from bleuart import BLEUARTClient
M5.begin()
identity=CONFIG["ble_identity"][1]
client=BLEUARTClient()
events=[]
client.irq(lambda *args:events.append("notify"))
client.connect("M5-API",timeout=12000)
deadline=time.ticks_add(time.ticks_ms(),20000)
while not client.is_connected() and time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
require(client.is_connected(),"original BLEUARTClient did not connect/discover NUS")
for api in ("bleuart.BLEUARTClient","bleuart.BLEUARTClient.connect","bleuart.BLEUARTClient.is_connected"):
 emit(api,"PASS",True,"original client scans, connects and discovers actual owned peripheral NUS handles")
client.write(identity.encode())
emit("bleuart.BLEUARTClient.write","OBSERVED_PENDING_PERIPHERAL_WRITE",True,"exact payload must independently arrive at owned peripheral GATT writer")
deadline=time.ticks_add(time.ticks_ms(),3000)
while client.any()<len(identity)+4 and time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
check("bleuart.BLEUARTClient.any",client.any,lambda value:value==len(identity)+4,"actual peripheral ACK notification byte count")
check("bleuart.BLEUARTClient.irq",lambda:bool(events),lambda value:value,"original client callback follows actual peripheral notification")
if client.any():
 first=client.read(4);rest=client.readline(max_size=len(identity))
 check("bleuart.BLEUARTClient.read",lambda:bytes(first).decode(),lambda value:value=="ACK:","actual notification prefix read from original client queue")
 check("bleuart.BLEUARTClient.readline",lambda:bytes(rest).decode(),lambda value:value==identity,"bounded original readline reads exact remainder of real notification")
else:
 for api in ("bleuart.BLEUARTClient.read","bleuart.BLEUARTClient.readline"):
  emit(api,"FAIL",False,"actual notification absent; original receive methods cannot satisfy payload oracle")
client.close();time.sleep_ms(200)
check("bleuart.BLEUARTClient.close",client.is_connected,lambda value:not value,"actual peripheral connection closed and wrapper connection state clears")
check("bleuart.BLEUARTClient.deinit",lambda:(client.deinit(),client._ble.active())[1],lambda value:value is False,"native BLE deactivated after real client session")
'''


ESPNOW='''import M5,struct
from m5espnow import M5ESPNow
M5.begin()
node=M5ESPNow(0)
print("SYSTEM_EXPORT "+json.dumps({"path":"m5espnow.M5ESPNow","members":[[name,type(getattr(node,name)).__name__,callable(getattr(node,name))]for name in dir(node)if not name.startswith("_")]}))
emit("m5espnow.M5ESPNow","STATE_PASS",bool(node.active()),"original ESPNow runtime initialized; no peer delivery inferred")
for name,arg,expected in (("_bytes_to_hex_str",b"\\x00\\xab\\xff","00ABFF"),("_hex_str_to_bytes","00aBff",b"\\x00\\xab\\xff"),("_to_bytes",16909060,b"\\x04\\x03\\x02\\x01"),("convert_to_bytes",[1,127,255],b"\\x01\\x7f\\xff")):
 check("m5espnow.M5ESPNow."+name,lambda name=name,arg=arg:getattr(node,name)(arg)==expected,lambda value:value,"independent documented byte-order/hex/list golden vector")
check("m5espnow.M5ESPNow._bytes_to",lambda:node._bytes_to(b"\\x04\\x03\\x02\\x01",0)==16909060 and node._bytes_to(b"\\x3f\\xc0\\x00\\x00",1)==1.5,lambda value:value,"independent little-endian integer and IEEE754 big-endian float golden vectors")
check("m5espnow.M5ESPNow.get_mac",lambda:all(node.get_mac(index)==interface.config("mac") and len(node.get_mac(index))==6 for index,interface in ((0,node.wlan_sta),(1,node.wlan_ap))),lambda value:value,"both interfaces match native WLAN MAC values without publishing device identifiers")
scan=node.wlan_sta.scan();fixture=next(row for row in scan if row[0]==b"myssid")
check("m5espnow.M5ESPNow.get_remote_mac",lambda:node.get_remote_mac(1,"myssid")==fixture[1] and node.get_remote_mac(0,"myssid")==fixture[2],lambda value:value,"wrapper remote BSSID/channel equals separately captured actual controller scan result")
node.set_ap_ssid("M5-API-ESPNOW")
emit("m5espnow.M5ESPNow.set_ap_ssid","STATE_PASS",node.wlan_ap.config("essid")=="M5-API-ESPNOW","native AP configuration readback; beacon/association data plane is separate")
peer=b"\\x02\\x00\\x00\\x00\\x00\\x42"
node.set_add_peer("020000000042",1,0,False)
emit("m5espnow.M5ESPNow.set_add_peer","STATE_PASS",any(row[0]==peer for row in node.get_peers()),"actual native ESPNow peer table contains the synthetic fixture address")
check("m5espnow.M5ESPNow.get_peer_list",lambda:node.get_peer_list(),lambda value:value==["020000000042"],"wrapper list matches independently configured synthetic peer")
node.set_pmk_encrypt(b"0123456789abcdef")
emit("m5espnow.M5ESPNow.set_pmk_encrypt","CONFIGURED_UNVERIFIED",True,"fixed non-secret test PMK accepted; encrypted peer delivery requires missing ESPNow controller peer model")
irq_events=[]
node.set_irq_callback(lambda obj:irq_events.append(True))
if CONFIG.get("espnow_loopback"):
 payload=b"ESPNOW-OWNED"
 error=None
 try:node.send_data(1,payload)
 except Exception as failure:error=repr(failure)
 deadline=time.ticks_add(time.ticks_ms(),2000)
 while not node.any() and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
 received=node.recv_data(1000) if node.any() else (None,None)
 unicast_ok=(error is None and received[0]==peer and bytes(received[1])==payload)
 emit("m5espnow.M5ESPNow.send_data","PASS" if unicast_ok else "FAIL",unicast_ok,"sent bytes were delivered through controller DMA and returned by the owned virtual ESP-NOW peer echo",error)
 emit("m5espnow.M5ESPNow.recv_data","PASS" if unicast_ok else "FAIL",unicast_ok,"original recv_data returned exact peer MAC and payload from controller RX DMA")
 error=None
 try:node.broadcast_data(payload)
 except Exception as failure:error=repr(failure)
 deadline=time.ticks_add(time.ticks_ms(),2000)
 while not node.any() and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
 received=node.recv_data(1000) if node.any() else (None,None)
 broadcast_ok=(error is None and received[0]==peer and bytes(received[1])==payload)
 emit("m5espnow.M5ESPNow.broadcast_data","PASS" if broadcast_ok else "FAIL",broadcast_ok,"broadcast action frame traversed controller TX DMA and the virtual peer returned exact payload through RX DMA",error)
 emit("m5espnow.M5ESPNow.set_irq_callback","PASS" if len(irq_events)>=2 else "FAIL",len(irq_events),"original IRQ callback fired for independent controller-delivered unicast and broadcast echoes")
else:
 for api,action in (("send_data",lambda:node.send_data(1,b"ESPNOW-OWNED")),("broadcast_data",lambda:node.broadcast_data(b"ESPNOW-OWNED")),("recv_data",lambda:node.recv_data(100))):
  try:action();error=None
  except Exception as failure:error=repr(failure)
  emit("m5espnow.M5ESPNow."+api,"BLOCKED_MODEL",None,"QEMU OpenMAC management dispatcher has no vendor-action/ESPNow peer RX route; return/state cannot prove payload delivery",error)
 emit("m5espnow.M5ESPNow.set_irq_callback","BLOCKED_MODEL",None,"no controller-delivered ESPNow packet available to trigger the original registered IRQ")
node.set_delete_peer(1)
emit("m5espnow.M5ESPNow.set_delete_peer","STATE_PASS",all(row[0]!=peer for row in node.get_peers()),"synthetic unicast peer removed from actual native table")
node.deinit()
emit("m5espnow.M5ESPNow.deinit","STATE_PASS",node.active() is False,"original deinit disables native ESPNow; peer_count cannot be queried while inactive")
'''


ESPNOW_NATIVE='''import espnow
from m5espnow import M5ESPNow
peer=b"\\x02\\x00\\x00\\x00\\x00\\x43"
for prefix,factory in (("espnow.ESPNow",espnow.ESPNow),("espnow.ESPNowBase",espnow.ESPNowBase),("m5espnow.M5ESPNow",M5ESPNow)):
 obj=factory()
 obj.active(True)
 emit(prefix,"STATE_PASS",obj.active(),"original native ESPNow instance activates on guest WLAN")
 emit(prefix+".active","STATE_PASS",obj.active(),"native activation getter reflects enabled stack; payload path is separate")
 obj.config(rxbuf=4096,timeout_ms=125)
 emit(prefix+".config","STATE_PASS",obj.config("rxbuf")==4096 and obj.config("timeout_ms")==125,"independent native buffer/timeout readback")
 obj.add_peer(peer,channel=0,ifidx=0,encrypt=False)
 emit(prefix+".add_peer","STATE_PASS",any(row[0]==peer for row in obj.get_peers()),"actual native peer table receives synthetic fixture entry")
 check(prefix+".get_peers",lambda:len(obj.get_peers()),lambda value:value==1,"native table enumerates exact configured synthetic peer count")
 check(prefix+".get_peer",lambda:obj.get_peer(peer)[0]==peer,lambda value:value,"native keyed peer lookup returns independently configured fixture")
 check(prefix+".peer_count",lambda:list(obj.peer_count()),lambda value:value==[1,0],"one unencrypted peer and zero encrypted peers configured")
 obj.mod_peer(peer,channel=1)
 emit(prefix+".mod_peer","STATE_PASS",obj.get_peer(peer)[2]==1,"native peer update independently read back through keyed lookup")
 emit(prefix+".any","STATE_PASS",obj.any() is False,"empty native RX queue observed before any peer packet; positive delivery is separate")
 check(prefix+".stats",lambda:list(obj.stats()),lambda value:len(value)==5 and all(type(number)==int for number in value),"five native counters: tx packets/responses/failures, rx packets/drops; no receive delivery inferred")
 obj.set_pmk(b"0123456789abcdef")
 emit(prefix+".set_pmk","CONFIGURED_UNVERIFIED",True,"fixed non-secret test PMK accepted; no encrypted message delivery proof")
 irq_events=[]
 obj.irq(lambda node:irq_events.append(True))
 if CONFIG.get("espnow_loopback"):
  payload=b"ESPNOW-NATIVE"
  slot=[None,bytearray(250)]
  error=None
  try:obj.send(peer,payload,False)
  except Exception as failure:error=repr(failure)
  deadline=time.ticks_add(time.ticks_ms(),2000)
  while not obj.any() and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
  count=obj.recvinto(slot,2000)
  received=bytes(slot[1][:count]) if count else b""
  passed=(error is None and count==len(payload) and received==payload and slot[0]==peer)
  emit(prefix+".send","PASS" if passed else "FAIL",passed,"original send traversed controller TX DMA and reached the owned virtual ESP-NOW peer echo",error)
  emit(prefix+".recvinto","PASS" if passed else "FAIL",passed,"original recvinto returned exact peer MAC and payload from controller RX DMA")
  emit(prefix+".irq","PASS" if irq_events else "FAIL",len(irq_events),"original IRQ callback fired after controller-delivered ESP-NOW action frame")
 else:
  for method in ("send","recvinto","irq")+(("recv","irecv")if prefix=="espnow.ESPNow"else()):
   try:
    if method=="send":obj.send(peer,b"ESPNOW-NATIVE",False)
    elif method=="recvinto":obj.recvinto([None,bytearray(250)],10)
    elif method in ("recv","irecv"):getattr(obj,method)(10)
    error=None
   except Exception as failure:error=repr(failure)
   emit(prefix+"."+method,"BLOCKED_MODEL",None,"OpenMAC lacks vendor-action/ESPNow controller peer TX/RX path; no payload or IRQ delivery is inferred",error)
 obj.del_peer(peer)
 emit(prefix+".del_peer","STATE_PASS",obj.peer_count()==(0,0),"synthetic peer actually removed from native ESPNow table")
 obj.active(False)
'''


M5BLE_CLIENT='''import M5,bluetooth
from m5ble import M5BLE
M5.begin()
identity=CONFIG["ble_identity"][1]
device=M5BLE.Device(name="M5-Client")
client=device.client
found=[];scanned=[];connected=[];disconnected=[];notified=[];readback=[]
client.on_server_found(lambda args:found.append(args[1]))
client.on_scan_finished(lambda args:scanned.append(args[1]))
client.on_connected(lambda value:connected.append(True))
client.on_disconnected(lambda args:disconnected.append(True))
client.on_notify(lambda value:notified.append(True))
client.on_read_complete(lambda value:readback.append(value))
client.scan(timeout=1500,connect_on_found=True,target_name_prefix="M5-API")
deadline=time.ticks_add(time.ticks_ms(),5000)
while (not found or not scanned)and time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
require(found,"actual owned peripheral advertisement absent")
for api,passed in (("scan",bool(scanned)),("on_server_found",bool(found)),("on_scan_finished",bool(scanned))):
 emit("m5ble.m5ble.Client."+api,"PASS"if passed else"FAIL",passed,"original callback follows real owned peripheral advertising and bounded scan completion")
deadline=time.ticks_add(time.ticks_ms(),10000)
while not connected and time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
require(connected,"original m5ble client connection/discovery callback absent")
for api in ("m5ble.m5ble.Device","m5ble.m5ble.Client","m5ble.m5ble.Client.connect","m5ble.m5ble.Client.on_connected"):
 emit(api,"PASS",True,"original Device/client completes actual GATT discovery of owned peripheral")
service="6E400001-B5A3-F393-E0A9-E50E24DCCA9E";rx="6E400002-B5A3-F393-E0A9-E50E24DCCA9E";tx="6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
check("m5ble.m5ble.Client.get_services",lambda:list(client.get_services()),lambda value:str(bluetooth.UUID(service))in value,"independently known owned NUS service found through actual GATT discovery")
check("m5ble.m5ble.Client.get_characteristics",lambda:list(client.get_characteristics(service)),lambda value:all(str(bluetooth.UUID(uuid))in value for uuid in (rx,tx)),"both known independent characteristic UUIDs discovered")
client.set_current_service_uuid(service)
emit("m5ble.m5ble.Client.set_current_service_uuid","PASS",client._current_service_uuid==service,"next original write resolves RX using configured default service")
client.set_mtu(80);time.sleep_ms(500)
check("m5ble.m5ble.Client.set_mtu",device.get_mtu,lambda value:value==80,"native ATT exchange negotiates the requested80byte MTU with real peer")
client.write(identity.encode(),rx)
emit("m5ble.m5ble.Client.write","OBSERVED_PENDING_PERIPHERAL_WRITE",True,"exact guest bytes must independently reach owned peripheral GATT writer")
device._ble.gattc_read(client._server_conn_handle,client._get_value_handle(rx))
deadline=time.ticks_add(time.ticks_ms(),3000)
while time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(20)
check("m5ble.m5ble.Client.on_read_complete",lambda:bool(readback),lambda value:value,"original wrapper callback must deliver actual successful native GATTC read result")
check("m5ble.m5ble.Client.any",lambda:client.any(tx),lambda value:value==len(identity)+4,"actual subscribed ACK notification must enter original receive queue")
check("m5ble.m5ble.Client.on_notify",lambda:bool(notified),lambda value:value,"original notify callback follows actual peer ATT notification")
check("m5ble.m5ble.Client.read",lambda:bytes(client.read(tx)).decode(),lambda value:value=="ACK:"+identity,"original buffer read returns exact peer notification bytes")
client.close();time.sleep_ms(500)
check("m5ble.m5ble.Client.close",lambda:client._server_conn_handle,lambda value:value is None,"original client clears actual connection handle after GAP disconnection")
check("m5ble.m5ble.Client.on_disconnected",lambda:bool(disconnected),lambda value:value,"actual GAP teardown dispatches original disconnect callback")
check("m5ble.m5ble.Device.deinit",lambda:(device.deinit(),device._ble.active())[1],lambda value:value is False,"native BLE deactivation returns after actual client exchange")
'''


TLS='''import ssl,binascii,os,machine
machine.RTC().datetime((CONFIG.get("tls_clock_year",2026),10,27,1,12,0,0,0))
print("PROTOCOL_TLS_CLOCK "+json.dumps({"time":time.time(),"gmtime":list(time.gmtime()),"rtc":list(machine.RTC().datetime()),"epoch":list(time.gmtime(0))}))
cert_path="/flash/owned-tls-certificate.pem";key_path="/flash/owned-tls-key.pem"
with open(cert_path,"w")as handle:handle.write(CONFIG["tls_certificate_pem"])
with open(key_path,"w")as handle:handle.write(CONFIG["tls_key_pem"])
certificate=binascii.unhexlify(CONFIG["tls_certificate_der"])
def exchange(wrapped):
 wrapped.write(b"GET /tls-authenticated HTTP/1.0\\r\\nHost: m5-api.test\\r\\n\\r\\n")
 response=bytearray()
 while True:
  data=wrapped.read(512)
  if not data:break
  response.extend(data)
 wrapped.close()
 require(b"200 OK"in response and b"X-Protocol-Fixture: yes"in response,"authenticated TLS HTTP bytes absent")
 return True
context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.verify_mode=ssl.CERT_REQUIRED
context.load_verify_locations(cadata=certificate)
context.load_cert_chain(cert_path,key_path)
sock=socket.socket();sock.settimeout(10);sock.connect(("10.0.2.2",CONFIG["tls"]))
context_pass=check("ssl.SSLContext.wrap_socket",lambda:exchange(context.wrap_socket(sock,server_hostname="m5-api.test")),lambda value:value,"actual TLS handshake validates owned server name/CA and independently owned server authenticates exact client certificate before HTTP exchange")
for api in ("ssl.SSLContext","ssl.SSLContext.load_verify_locations","ssl.SSLContext.load_cert_chain"):
 emit(api,"PASS"if context_pass else"STATE_PASS",True,"constructor and configured CA/client key are accepted; complete authenticated data plane is required for functional PASS")
try:sock.close()
except OSError:pass
sock=socket.socket();sock.settimeout(10);sock.connect(("10.0.2.2",CONFIG["tls"]))
check("ssl.wrap_socket",lambda:exchange(ssl.wrap_socket(sock,key=key_path,cert=cert_path,cert_reqs=ssl.CERT_REQUIRED,cadata=certificate,server_hostname="m5-api.test")),lambda value:value,"original public SSL wrapper performs independent mutually authenticated TLS HTTP exchange")
try:sock.close()
except OSError:pass
os.remove(cert_path);os.remove(key_path)
'''


RTU_SLAVE='''import modbus,machine
uart=machine.UART(1,baudrate=9600,tx=2,rx=1,timeout=10)
server=modbus.ModbusRTUSlave(uart,device_address=1)
print("SYSTEM_EXPORT "+json.dumps({"path":"modbus.ModbusRTUSlave","members":[[name,type(getattr(server,name)).__name__,callable(getattr(server,name))]for name in dir(server)if not name.startswith("_")]}))
events=[]
for event in (server.READ_COILS_EVENT,server.READ_DISCRETE_INPUTS_EVENT,server.READ_HOLDING_REGISTERS_EVENT,server.READ_INPUT_REGISTERS_EVENT):
 server.set_callback(event,lambda args:events.append(args))
server.start()
def wire(sequence):
 before=len(events)
 print("RTU_SLAVE_REQUEST "+json.dumps({"sequence":sequence}))
 deadline=time.ticks_add(time.ticks_ms(),5000)
 while len(events)==before and time.ticks_diff(deadline,time.ticks_ms())>0:server.tick();time.sleep_ms(5)
 require(len(events)>before,"actual UART master request did not dispatch callback")
def pending(api,sequences):
 emit(api,"OBSERVED_PENDING_UART_PEER",{"wire_sequences":sequences},"independent master must verify exact original slave UART TX bytes and CRC after actual RX FIFO request")
for group,(suffix,plural,initial,changed,multiple)in enumerate((("coil","coils",False,True,[True,False,True]),("discrete_input","discrete_input",False,True,[True,False,True]),("holding_register","holding_register",1234,4321,[901,902,903]),("input_register","input_register",1234,4321,[901,902,903]))):
 base=group*5
 for index in range(3):getattr(server,"add_"+suffix)(32+index,initial)
 wire(base)
 pending("modbus.ModbusRTUSlave.add_"+suffix,[base])
 require(getattr(server,"get_"+suffix)(32)==initial,"original context getter differs from independent requested value")
 pending("modbus.ModbusRTUSlave.get_"+suffix,[base])
 getattr(server,"set_"+suffix)(32,changed);wire(base+1)
 pending("modbus.ModbusRTUSlave.set_"+suffix,[base+1])
 getattr(server,"set_multi_"+plural)(32,multiple);wire(base+2)
 pending("modbus.ModbusRTUSlave.set_multi_"+plural,[base+2])
 getattr(server,"remove_"+suffix)(33)
 try:getattr(server,"get_"+suffix)(33);removed=False
 except KeyError:removed=True
 require(removed,"middle register remains after original remove")
 wire(base+3);wire(base+4)
 pending("modbus.ModbusRTUSlave.remove_"+suffix,[base+3,base+4])
for api in ("modbus.ModbusRTUSlave","modbus.ModbusRTUSlave.start","modbus.ModbusRTUSlave.tick","modbus.ModbusRTUSlave.set_callback"):
 pending(api,list(range(20)))
server.stop()
print("RTU_SLAVE_REQUEST "+json.dumps({"sequence":20}))
time.sleep_ms(1500);server.tick()
require(uart.any()>=8,"stopped slave did not retain the actual unprocessed UART request")
pending("modbus.ModbusRTUSlave.stop",[20])
server.set_callback(server.READ_HOLDING_REGISTERS_EVENT,lambda args:server.stop())
for sequence,method in ((21,"run"),(22,"run_async")):
 server.start()
 print("RTU_SLAVE_REQUEST "+json.dumps({"sequence":sequence}))
 if method=="run_async":
  import asyncio
  asyncio.run(server.run_async())
 else:server.run()
 pending("modbus.ModbusRTUSlave."+method,[sequence])
uart.deinit()
'''


PPP='''import machine
uart=machine.UART(1,baudrate=115200,tx=2,rx=1,timeout=10,rxbuf=2048)
link=network.PPP(uart)
print("SYSTEM_EXPORT "+json.dumps({"path":"network.PPP","members":[[name,type(getattr(link,name)).__name__,callable(getattr(link,name))]for name in dir(link)if not name.startswith("_")]}))
check("network.PPP.config",lambda:(link.config(stream=uart),link.config("stream")is uart)[1],lambda value:value,"native PPP stream setter/getter uses actual UART; later independent LCP/IPCP/UDP oracle is required")
if hasattr(link,"active"):link.active(True)
link.connect()
deadline=time.ticks_add(time.ticks_ms(),25000)
while not link.isconnected()and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
up=link.isconnected()
def udp():
 peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.settimeout(5)
 try:
  peer.sendto(b"PPP-NATIVE-DATAPLANE",("192.0.2.1",17073))
  return peer.recvfrom(128)[0]==b"PPP-NATIVE-DATAPLANE"
 finally:peer.close()
exchange=check("network.PPP.connect",lambda:up and udp(),lambda value:value,"actual native PPP must negotiate LCP/IPCP and deliver exact IPv4 UDP bytes to independent UART peer")
for api in ("network.PPP","network.PPP.active","network.PPP.isconnected","network.PPP.status"):
 emit(api,"OBSERVED_PENDING_PPP_PEER"if exchange else"FAIL",up,"constructor/activation/connected state must be backed by independent PPP frame CRC, IP negotiation and bidirectional UDP bytes")
check("network.PPP.ifconfig",lambda:list(link.ifconfig()),lambda value:up and value[0]=="192.0.2.2","PPP negotiated address matches independently assigned IPCP peer value")
check("network.PPP.ipconfig",lambda:list(link.ipconfig("addr4")),lambda value:up and value[0]=="192.0.2.2","PPP native IP config reflects actual independent IPCP negotiation")
if hasattr(link,"set_default"):
 check("network.PPP.set_default",lambda:(link.set_default(),udp())[1],lambda value:value,"selecting real PPP default route preserves independently verified UDP bytes")
link.disconnect()
deadline=time.ticks_add(time.ticks_ms(),3000)
while link.isconnected()and time.ticks_diff(deadline,time.ticks_ms())>0:time.sleep_ms(10)
check("network.PPP.disconnect",link.isconnected,lambda value:value is False,"actual PPP LCP termination clears native connected state")
if hasattr(link,"deinit"):
 check("network.PPP.deinit",lambda:(link.deinit(),link.active())[1],lambda value:value is False,"native PPP deinit releases original stream controller and connection")
else:link.active(False)
uart.deinit()
'''


def build_program(group, config):
    if group=="ppp":
        preface,body=PPP.split("link=network.PPP(uart)\n",1)
        admission='''try:link=network.PPP(uart)
except Exception as error:
 status="UNSUPPORTED_FIRMWARE"if isinstance(error,TypeError)and "can't create 'PPP' instances"in str(error)else"ERROR"
 for api in ["network.PPP"]+["network.PPP."+name for name in dir(network.PPP)if not name.startswith("_")and callable(getattr(network.PPP,name))]:
  emit(api,status,oracle="actual native UART-backed PPP construction failed before LCP/IPCP or any method data plane could run",error=repr(error))
 uart.deinit()
else:
'''
        return COMMON+"\n"+preface+admission+"\n".join(" "+line for line in body.splitlines())+"\nprint('PROTOCOL_GROUP_DONE ppp')\n"
    if group=="modbus-rtu-slave":
        return COMMON+"\nCONFIG="+repr(config)+"\n"+RTU_SLAVE+"\nprint('PROTOCOL_GROUP_DONE modbus-rtu-slave')\n"
    if group=="modbus-rtu":
        # Reuse the exact client operation recipes with the documented RTU factory.
        body=MODBUS.split('tcp=ModbusTCPFrame',1)[0]
        body=body.replace('modbus.ModbusTCPClient("10.0.2.2",CONFIG["modbus"])',
             'modbus.ModbusRTUMaster(uart_no=1,tx_pin=2,rx_pin=1,baudrate=9600)')
        body=body.replace('client.connect();client.sock.settimeout(5)','')
        body=body.replace('client.disconnect()','client.uart.deinit()')
        body=body.replace('emit("modbus.ModbusTCPClient.connect","PASS",True,"real TCP connection carries matching Modbus transaction ID and data")','')
        body=body.replace('check("modbus.ModbusTCPClient.disconnect",lambda:client.connected,lambda value:value is False,"closed actual TCP client clears connected state")','')
        body=body.replace('modbus.ModbusTCPClient','modbus.ModbusRTUMaster')
        body=body.replace('actual TCP','actual UART').replace('MBAP/PDU','RTU/CRC').replace('TCP wire','UART wire')
        return COMMON+"\nCONFIG="+repr(config)+"\n"+body+"\nprint('PROTOCOL_GROUP_DONE modbus-rtu')\n"
    if group in {"audio-player","audio-recorder"}:
        from probe_audio_wrappers import PLAYER,RECORDER
        body=PLAYER if group=="audio-player" else RECORDER
        case=config.get("audio_case","all")
        if group=="audio-player" and case!="all":
            prefix=PLAYER.split("data=pcm(660,1)",1)[0]
            if case=="raw":body=prefix+"data=pcm(660,1)"+PLAYER.split("data=pcm(660,1)",1)[1].split("def tone():",1)[0]
            elif case=="tone":body=prefix+"def tone():"+PLAYER.split("def tone():",1)[1].split("data=pcm(990,3)",1)[0]
            elif case=="file":body=prefix+"data=pcm(990,3)"+PLAYER.split("data=pcm(990,3)",1)[1]
        return COMMON+"\n"+body+"\nprint('PROTOCOL_GROUP_DONE "+group+"')\n"
    body = {"http": HTTP, "sockets": SOCKETS, "easysocket": EASY,"mqtt":MQTT,"network":NETWORK,"modbus":MODBUS,"modbus-candidate":MODBUS,"ezdata":EZDATA,"requests-candidate":REQUESTS_CORRECTION,"ble-nus":BLE_NUS,"m5ble-server":M5BLE_SERVER,"ble-client":BLE_CLIENT,"m5ble-client":M5BLE_CLIENT,"espnow":ESPNOW,"espnow-native":ESPNOW_NATIVE,"tls":TLS}[group]
    return COMMON + "\nCONFIG=" + repr(config) + "\nconnect_wifi()\n" + body + "\nprint('PROTOCOL_GROUP_DONE " + group + "')\n"


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group",choices=("http","sockets","easysocket","mqtt","network"),required=True)
    parser.add_argument("--http-port",type=int,default=18090)
    parser.add_argument("--tcp-port",type=int,default=18091)
    parser.add_argument("--udp-port",type=int,default=18092)
    parser.add_argument("--mqtt-port",type=int,default=1883)
    args=parser.parse_args()
    print(build_program(args.group,{"http":args.http_port,"tcp":args.tcp_port,"udp":args.udp_port,"mqtt":args.mqtt_port}))
