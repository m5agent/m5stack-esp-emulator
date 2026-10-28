"""Independent bounded PPP LCP/IPCP and IPv4 UDP echo over real Unit UART."""
from __future__ import annotations
import hashlib,struct


def fcs(raw):
    value=0xffff
    for byte in raw:
        value^=byte
        for _ in range(8):value=(value>>1)^0x8408 if value&1 else value>>1
    return value


def frame(protocol,payload):
    raw=b'\xff\x03'+struct.pack('!H',protocol)+payload
    raw+=struct.pack('<H',fcs(raw)^0xffff)
    return b'\x7e'+b''.join(bytes((0x7d,byte^0x20))if byte<0x20 or byte in(0x7d,0x7e)else bytes((byte,))for byte in raw)+b'\x7e'


def control(code,identifier,payload=b''):
    return bytes((code,identifier))+struct.pack('!H',len(payload)+4)+payload


def checksum(raw):
    if len(raw)%2:raw+=b'\x00'
    value=sum(struct.unpack('!'+str(len(raw)//2)+'H',raw))
    while value>>16:value=(value&0xffff)+(value>>16)
    return value^0xffff


class PPPControllerPeer:
    def __init__(self,records):
        self.records=records;self.offset=0;self.pending=bytearray();self.started=False;self.sent_ipcp=False

    def __call__(self,api,session_id,current):
        if current['state']!='running':return
        units=api.json(f'sessions/{session_id}/units')
        unit=next((row for row in units['units']if row['id']=='rtu'),None)
        if unit is None or not unit.get('available'):return
        raw=bytes.fromhex(unit['properties']['tx-hex']);self.pending.extend(raw[self.offset:]);self.offset=len(raw)
        def send(protocol,payload):
            raw=frame(protocol,payload)
            api.json(f'sessions/{session_id}/unit-input','POST',{'id':'rtu','values':{'rx-hex':raw.hex()}})
            self.records.append({'protocol':'PPP','direction':'peer-to-guest','ppp_protocol':protocol,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        while 0x7e in self.pending:
            end=self.pending.index(0x7e);escaped=bytes(self.pending[:end]);del self.pending[:end+1]
            if not escaped:continue
            decoded=bytearray();escape=False
            for byte in escaped:
                if escape:decoded.append(byte^0x20);escape=False
                elif byte==0x7d:escape=True
                else:decoded.append(byte)
            if len(decoded)<4 or fcs(decoded)!=0xf0b8:
                self.records.append({'protocol':'PPP','status':'INVALID_FCS','sha256':hashlib.sha256(decoded).hexdigest()});continue
            data=bytes(decoded[:-2]);data=data[2:]if data.startswith(b'\xff\x03')else data
            if data[0]&1:protocol=data[0];payload=data[1:]
            else:protocol=int.from_bytes(data[:2],'big');payload=data[2:]
            self.records.append({'protocol':'PPP','direction':'guest-to-peer','ppp_protocol':protocol,'bytes':len(decoded),'sha256':hashlib.sha256(decoded).hexdigest()})
            if protocol in(0xc021,0x8021,0x8057):
                code,identifier=payload[:2];length=int.from_bytes(payload[2:4],'big');options=payload[4:length]
                if protocol==0xc021:
                    if code==1:
                        send(protocol,control(2,identifier,options))
                        if not self.started:
                            self.started=True;send(protocol,control(1,0x61,b'\x01\x04\x05\xdc\x02\x06\x00\x00\x00\x00'))
                    elif code==2 and identifier==0x61 and not self.sent_ipcp:
                        self.sent_ipcp=True;send(0x8021,control(1,0x62,b'\x03\x06\xc0\x00\x02\x01'))
                    elif code==5:send(protocol,control(6,identifier,options))
                    elif code==9:send(protocol,control(10,identifier,options))
                elif protocol==0x8021 and code==1:
                    offset=0;nak=bytearray();reject=bytearray()
                    while offset<len(options):
                        kind,size=options[offset:offset+2];option=options[offset:offset+size]
                        if kind in(3,129,131):
                            wanted=b'\xc0\x00\x02\x02'if kind==3 else b'\xc0\x00\x02\x01'
                            if option[2:]!=wanted:nak.extend(bytes((kind,6))+wanted)
                        else:reject.extend(option)
                        offset+=size
                    send(protocol,control(4 if reject else 3 if nak else 2,identifier,bytes(reject or nak or options)))
                elif protocol==0x8057:send(0xc021,control(8,0x63,struct.pack('!H',protocol)+payload))
            elif protocol==0x21:
                ihl=(payload[0]&15)*4;total=int.from_bytes(payload[2:4],'big');packet=payload[:total]
                if payload[9]!=17 or checksum(packet[:ihl]):raise ValueError('owned PPP peer received invalid IPv4/UDP packet')
                source_port,destination_port,size,_=struct.unpack('!HHHH',packet[ihl:ihl+8]);body=packet[ihl+8:ihl+size]
                if packet[12:16]!=b'\xc0\x00\x02\x02'or packet[16:20]!=b'\xc0\x00\x02\x01'or destination_port!=17073 or body!=b'PPP-NATIVE-DATAPLANE':raise ValueError('PPP UDP payload/address golden oracle differs')
                udp=struct.pack('!HHHH',destination_port,source_port,len(body)+8,0)+body
                header=struct.pack('!BBHHHBBH4s4s',0x45,0,len(udp)+20,1,0,64,17,0,packet[16:20],packet[12:16])
                header=header[:10]+struct.pack('!H',checksum(header))+header[12:]
                send(0x21,header+udp)
                self.records.append({'protocol':'PPP-UDP-ORACLE','status':'PASS','payload_sha256':hashlib.sha256(body).hexdigest(),'ipv4_checksum':'PASS','source_ip':'192.0.2.2','peer_ip':'192.0.2.1'})
