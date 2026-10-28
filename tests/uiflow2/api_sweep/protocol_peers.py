"""Bounded deterministic wire peers for the original guest protocol libraries."""
from __future__ import annotations

import hashlib
import json
import socketserver
import struct
import time


def mqtt_packet(opcode, body=b""):
    length = len(body)
    encoded = bytearray([opcode])
    while True:
        digit = length & 127
        length >>= 7
        encoded.append(digit | (128 if length else 0))
        if not length:
            return bytes(encoded) + body


def mqtt_string(value):
    return struct.pack("!H", len(value)) + value


def mqtt_handler(records):
    class MQTTHandler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(20)
            subscriptions = set()

            def exact(length):
                result = b""
                while len(result) < length:
                    part = self.request.recv(length - len(result))
                    if not part:
                        raise EOFError("MQTT peer EOF")
                    result += part
                return result

            def send(opcode, body=b""):
                raw = mqtt_packet(opcode, body)
                self.request.sendall(raw)
                records.append({"protocol": "MQTT", "direction": "peer-to-guest",
                                "opcode": opcode, "bytes": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest()})

            try:
                while True:
                    opcode = exact(1)[0]
                    length, multiplier = 0, 1
                    for _ in range(4):
                        digit = exact(1)[0]
                        length += (digit & 127) * multiplier
                        if not digit & 128:
                            break
                        multiplier *= 128
                    else:
                        raise ValueError("invalid MQTT length")
                    if length > 65536:
                        raise ValueError("MQTT fixture packet exceeds bound")
                    body = exact(length)
                    raw = mqtt_packet(opcode, body)
                    row = {"protocol": "MQTT", "direction": "guest-to-peer", "opcode": opcode,
                           "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    records.append(row)
                    kind = opcode >> 4
                    if kind == 1:
                        if body[:7] != b"\x00\x04MQTT\x04":
                            raise ValueError("fixture requires MQTT 3.1.1")
                        flags, offset = body[7], 10
                        fields = []
                        while offset < len(body):
                            size = int.from_bytes(body[offset:offset + 2], "big")
                            offset += 2
                            fields.append(body[offset:offset + size].decode())
                            offset += size
                        row.update(connect_flags=flags, connect_fields=fields)
                        send(0x20, b"\x00\x00")
                    elif kind == 8:
                        packet_id = body[:2]
                        size = int.from_bytes(body[2:4], "big")
                        topic = body[4:4 + size]
                        subscriptions.add(topic)
                        row["topic"] = topic.decode()
                        send(0x90, packet_id + b"\x00")
                    elif kind == 3:
                        size = int.from_bytes(body[:2], "big")
                        topic, offset = body[2:2 + size], 2 + size
                        qos = (opcode >> 1) & 3
                        if qos == 1:
                            send(0x40, body[offset:offset + 2])
                            offset += 2
                        elif qos:
                            raise ValueError("fixture supports QoS 0 and 1")
                        message = body[offset:]
                        row.update(topic=topic.decode(), payload_sha256=hashlib.sha256(message).hexdigest())
                        if topic in subscriptions:
                            send(0x30, mqtt_string(topic) + message)
                    elif kind == 10:
                        size = int.from_bytes(body[2:4], "big")
                        subscriptions.discard(body[4:4 + size])
                        send(0xB0, body[:2])
                    elif kind == 12:
                        send(0xD0)
                    elif kind == 14:
                        return
                    else:
                        raise ValueError("unexpected MQTT opcode")
            except (EOFError, TimeoutError, ConnectionError, OSError):
                return

    return MQTTHandler


def modbus_handler(records):
    class ModbusHandler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(20)
            coils = {index: bool(index % 2) for index in range(128)}
            registers = {index: 1000 + index for index in range(128)}

            def exact(length):
                result = b""
                while len(result) < length:
                    part = self.request.recv(length - len(result))
                    if not part:
                        raise EOFError("Modbus peer EOF")
                    result += part
                return result

            try:
                while True:
                    header = exact(7)
                    transaction, protocol, length, unit = struct.unpack("!HHHB", header)
                    if protocol or not 2 <= length <= 254:
                        raise ValueError("invalid Modbus MBAP")
                    pdu = exact(length - 1)
                    code, address, value = struct.unpack("!BHH", pdu[:5])
                    if code in (1, 2):
                        bits = [coils[address + index] for index in range(value)]
                        data = bytes(sum(int(bit) << index for index, bit in enumerate(bits[offset:offset + 8]))
                                     for offset in range(0, value, 8))
                        response = bytes([code, len(data)]) + data
                    elif code in (3, 4):
                        data = b"".join(struct.pack("!H", registers[address + index]) for index in range(value))
                        response = bytes([code, len(data)]) + data
                    elif code in (5, 6):
                        if code == 5:
                            coils[address] = value == 0xff00
                        else:
                            registers[address] = value
                        response = pdu
                    elif code in (15, 16):
                        for index in range(value):
                            if code == 15:
                                coils[address + index] = bool(pdu[6 + index // 8] & (1 << (index % 8)))
                            else:
                                registers[address + index] = int.from_bytes(pdu[6 + index * 2:8 + index * 2], "big")
                        response = pdu[:5]
                    else:
                        response = bytes([code | 128, 1])
                    raw = struct.pack("!HHHB", transaction, 0, len(response) + 1, unit) + response
                    records.append({"protocol": "ModbusTCP", "function_code": code, "register": address,
                                    "request_sha256": hashlib.sha256(header + pdu).hexdigest(),
                                    "response_sha256": hashlib.sha256(raw).hexdigest()})
                    self.request.sendall(raw)
            except (EOFError, TimeoutError, ConnectionError, OSError):
                return

    return ModbusHandler


def rtu_crc(payload):
    crc=0xffff
    for octet in payload:
        crc^=octet
        for _ in range(8):
            crc=(crc>>1)^0xa001 if crc&1 else crc>>1
    return struct.pack("<H",crc)


class RTUControllerPeer:
    """A real UART external peer: observe TX bytes and inject RX FIFO bytes."""
    def __init__(self,records):
        self.records=records
        self.offset=0
        self.coils={index:bool(index%2) for index in range(128)}
        self.registers={index:1000+index for index in range(128)}

    def __call__(self,api,session_id,current):
        if current["state"]!="running":return
        snapshot=api.json(f"sessions/{session_id}/units")
        unit=next((unit for unit in snapshot["units"] if unit["id"]=="rtu"),None)
        if unit is None or not unit.get("available"):return
        raw=bytes.fromhex(unit["properties"]["tx-hex"])
        while len(raw)-self.offset>=8:
            pending=raw[self.offset:]
            code=pending[1]
            length=9+pending[6] if code in (15,16) else 8
            if len(pending)<length:return
            request=pending[:length]
            if rtu_crc(request[:-2])!=request[-2:]:raise ValueError("actual RTU TX CRC differs")
            self.offset+=length
            address,value=struct.unpack("!HH",request[2:6])
            if code in (1,2):
                data=bytes(sum(int(self.coils[address+i])<<(i%8) for i in range(offset,min(offset+8,value))) for offset in range(0,value,8))
                response=bytes([request[0],code,len(data)])+data
            elif code in (3,4):
                data=b"".join(struct.pack("!H",self.registers[address+i])for i in range(value))
                response=bytes([request[0],code,len(data)])+data
            elif code in (5,6):
                if code==5:self.coils[address]=value==0xff00
                else:self.registers[address]=value
                response=request[:-2]
            elif code in (15,16):
                for i in range(value):
                    if code==15:self.coils[address+i]=bool(request[7+i//8]&(1<<(i%8)))
                    else:self.registers[address+i]=int.from_bytes(request[7+2*i:9+2*i],"big")
                response=request[:6]
            else:raise ValueError("unexpected actual RTU function")
            response+=rtu_crc(response)
            api.json(f"sessions/{session_id}/unit-input","POST",{"id":"rtu","values":{"rx-hex":response.hex()}})
            self.records.append({"protocol":"ModbusRTU","function_code":code,"register":address,
                "request_sha256":hashlib.sha256(request).hexdigest(),"response_sha256":hashlib.sha256(response).hexdigest(),
                "observed_tx_offset":self.offset,"transport":"actual emulated UART TX / injected external peer RX FIFO"})


class RTUSlaveControllerPeer:
    """Independent master requests over the attached real UART FIFO model."""
    def __init__(self,records):
        self.records=records;self.offset=0;self.serial_offset=0;self.serial_tail="";self.queue=[];self.pending=None

    def __call__(self,api,session_id,current):
        if current["state"]!="running":return
        serial=api.json(f"sessions/{session_id}/serial?offset={self.serial_offset}&limit=65536")
        self.serial_offset=serial["next_offset"]
        combined=self.serial_tail+serial["data"]
        complete,separator,tail=combined.rpartition("\n")
        self.serial_tail=tail if separator else combined
        if not separator:complete=""
        for line in complete.splitlines():
            if line.startswith("RTU_SLAVE_REQUEST "):
                self.queue.append(json.loads(line.split(" ",1)[1]))
        snapshot=api.json(f"sessions/{session_id}/units")
        unit=next((row for row in snapshot["units"]if row["id"]=="rtu"),None)
        if unit is None or not unit.get("available"):return
        raw=bytes.fromhex(unit["properties"]["tx-hex"])
        if self.pending is not None:
            row=self.pending;sequence=row["sequence"]
            if sequence==20:
                if time.monotonic()-row["injected"]>.25:
                    self.records.append({"protocol":"ModbusRTUSlave","sequence":20,"status":"PASS"if len(raw)==self.offset else"FAIL",
                        "oracle":"stopped original slave emitted no UART TX response to actual injected request"})
                    self.pending=None
            elif len(raw)>self.offset+2:
                length=5+raw[self.offset+2]
                if len(raw)-self.offset>=length:
                    response=raw[self.offset:self.offset+length];self.offset+=length
                    group,phase=divmod(sequence,5);code=3 if sequence>20 else group+1
                    bit=code in (1,2)
                    expected=([False]*3 if bit else[1234]*3)if phase==0 else([True]if bit else[4321])if phase==1 else([True,False,True]if bit else[901,902,903])if phase==2 else([True]if bit else[901])if phase==3 else([True]if bit else[903])
                    if sequence>20:expected=[901]
                    actual=[bool(response[3+index//8]&(1<<(index%8)))for index in range(len(expected))]if bit else[int.from_bytes(response[3+2*index:5+2*index],"big")for index in range(len(expected))]
                    passed=(response[:2]==bytes([1,code])and rtu_crc(response[:-2])==response[-2:]and actual==expected)
                    self.records.append({"protocol":"ModbusRTUSlave","sequence":sequence,"status":"PASS"if passed else"FAIL",
                        "request_sha256":row["request_sha256"],"response_sha256":hashlib.sha256(response).hexdigest(),"actual":actual,"expected":expected,
                        "transport":"actual Unit UART RX injection / observed original slave UART TX with CRC16"})
                    self.pending=None
        if self.pending is None and self.queue:
            row=self.queue.pop(0);sequence=row["sequence"]
            group,phase=divmod(min(sequence,19),5);code=group+1 if sequence<20 else 3
            address=34 if phase==4 and sequence<20 else 32
            quantity=3 if phase in (0,2)and sequence<20 else 1
            request=struct.pack("!BBHH",1,code,address,quantity);request+=rtu_crc(request)
            api.json(f"sessions/{session_id}/unit-input","POST",{"id":"rtu","values":{"rx-hex":request.hex()}})
            self.pending={"sequence":sequence,"injected":time.monotonic(),"request_sha256":hashlib.sha256(request).hexdigest()}
