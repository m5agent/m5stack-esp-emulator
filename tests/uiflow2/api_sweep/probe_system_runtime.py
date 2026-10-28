"""Stock native filesystem, scheduling and readiness APIs in the real guest.

The RAM block devices are ordinary user supplied VFS inputs. Their results test
native filesystem algorithms, and do not claim a physical SD/controller path.
"""
import os,sys,time,json,io,socket,select,network,bluetooth,gc


def result(api,action,verify,oracle,status="PASS"):
    try:
        value=action()
        passed=verify(value)
        print("SYSTEM_API "+json.dumps({"api":api,"status":status if passed else "FAIL","value":value,"oracle":oracle}))
        return value
    except Exception as error:
        print("SYSTEM_API "+json.dumps({"api":api,"status":"ERROR","error":repr(error),"oracle":oracle}))


class Blocks:
    def __init__(self):self.data=bytearray(512*128)
    def readblocks(self,block,buf,offset=0):
        start=block*512+offset;buf[:]=self.data[start:start+len(buf)];return 0
    def writeblocks(self,block,buf,offset=None):
        start=block*512+(offset or 0)
        if offset is None:self.data[start:start+len(buf)]=buf
        else:self.data[start:start+len(buf)]=buf
        return 0
    def ioctl(self,operation,arg):
        if operation==4:return len(self.data)//512
        if operation==5:return 512
        if operation==6:self.data[arg*512:(arg+1)*512]=b"\xff"*512
        return 0


def filesystems():
    for name in ("VfsFat","VfsLfs2"):
        cls=getattr(os,name);prefix="os."+name
        blocks=Blocks();cls.mkfs(blocks);vfs=cls(blocks)
        print("SYSTEM_EXPORT "+json.dumps({"path":prefix,"members":[[key,type(getattr(vfs,key)).__name__,callable(getattr(vfs,key))]for key in dir(vfs)if not key.startswith("_")]}))
        vfs.mkdir("fixture");vfs.chdir("fixture")
        result(prefix+".getcwd",vfs.getcwd,lambda value:value=="/fixture","native RAM-backed filesystem directory state")
        result(prefix+".mkdir",lambda:"fixture"in vfs.listdir("/")if hasattr(vfs,"listdir")else any(row[0]=="fixture"for row in vfs.ilistdir("/")),lambda value:value,"new directory appears in independent native iterator")
        result(prefix+".chdir",vfs.getcwd,lambda value:value=="/fixture","subsequent relative I/O resolves inside selected directory")
        with vfs.open("fixture.bin","wb")as handle:handle.write(b"NATIVE-VFS\x00\xff")
        with vfs.open("fixture.bin","rb")as handle:readback=handle.read()
        for api in (prefix,prefix+".mkfs",prefix+".open"):
            result(api,lambda:readback==b"NATIVE-VFS\x00\xff",lambda value:value,"original native filesystem formats/mounts and persists exact binary bytes through ordinary block protocol")
        result(prefix+".ilistdir",lambda:[row[0]for row in vfs.ilistdir(".")],lambda value:"fixture.bin"in value,"native inode iterator sees actual written file")
        result(prefix+".stat",lambda:vfs.stat("fixture.bin")[6],lambda value:value==12,"native file size equals independent fixture byte count")
        result(prefix+".statvfs",lambda:list(vfs.statvfs(".")),lambda value:len(value)==10 and value[0]>0,"native filesystem capacity metadata")
        vfs.rename("fixture.bin","renamed.bin")
        result(prefix+".rename",lambda:[row[0]for row in vfs.ilistdir(".")],lambda value:"renamed.bin"in value and "fixture.bin"not in value,"native renamed inode remains reachable")
        vfs.umount();vfs.mount(False,False)
        with vfs.open("/fixture/renamed.bin","rb")as handle:persisted=handle.read()
        for api in (prefix+".mount",prefix+".umount"):
            result(api,lambda:persisted==readback,lambda value:value,"real remount preserves native filesystem bytes in independent RAM block storage")
        vfs.remove("/fixture/renamed.bin")
        result(prefix+".remove",lambda:list(vfs.ilistdir("/fixture")),lambda value:not value,"written native inode removed")
        vfs.chdir("/");vfs.rmdir("fixture")
        result(prefix+".rmdir",lambda:list(vfs.ilistdir("/")),lambda value:not value,"empty native directory removed")
        mountpoint="/api-ram-"+name.lower()
        os.mount(vfs,mountpoint)
        with open(mountpoint+"/global.bin","wb")as handle:handle.write(b"GLOBAL-VFS")
        with open(mountpoint+"/global.bin","rb")as handle:global_readback=handle.read()
        result("os.mount",lambda:global_readback==b"GLOBAL-VFS",lambda value:value,"global namespace routes actual file I/O into native RAM-backed VFS")
        os.umount(mountpoint)
        def absent():
            try:os.stat(mountpoint+"/global.bin");return False
            except OSError:return True
        result("os.umount",absent,lambda value:value,"unmounted filesystem disappears from global namespace")
        del vfs,blocks
        gc.collect()


def global_filesystem():
    path="/flash/api-runtime-fixture";original=os.getcwd()
    os.mkdir(path)
    result("os.mkdir",lambda:path.rsplit("/",1)[1]in os.listdir("/flash"),lambda value:value,"new persistent filesystem directory appears")
    os.chdir(path)
    result("os.chdir",os.getcwd,lambda value:value==path,"subsequent relative file I/O is rooted at requested directory")
    with open("unlink.bin","wb")as handle:handle.write(b"unlink")
    result("os.ilistdir",lambda:[row[0]for row in os.ilistdir(".")],lambda value:"unlink.bin"in value,"actual flash file listed by native iterator")
    os.unlink("unlink.bin")
    result("os.unlink",os.listdir,lambda value:"unlink.bin"not in value,"actual flash inode removed through unlink alias")
    result("os.sync",os.sync,lambda value:value is None,"native filesystem flush returns after actual flash writes")
    os.chdir(original);os.rmdir(path)
    result("os.rmdir",lambda:path.rsplit("/",1)[1]not in os.listdir("/flash"),lambda value:value,"native flash directory removed")
    result("os.uname",lambda:list(os.uname()),lambda value:len(value)==5 and any(name in value[4] for name in ("StopWatch","StickS3","Core2")),"runtime-provided machine identity names the selected board family")
    first=os.urandom(64)
    result("os.urandom",lambda:len(os.urandom(64))==64 and os.urandom(64)!=first,lambda value:value,"independent native entropy calls have requested length and differing bytes; no cryptographic-quality claim")
    def dupterm_state():
        try:original=os.dupterm(None,0)
        except OSError as error:
            if "Core2"in os.uname()[4]:return "unsupported-native-uart0"
            raise
        os.dupterm(original,0)
        return "supported"
    result("os.dupterm",dupterm_state,lambda value:value in ("supported","unsupported-native-uart0"),"UART stream roundtrip or Core2 native-UART0 EPERM boundary is explicit; full reattach remains separate","STATE_PASS")


def readiness():
    listener=socket.socket();listener.bind(("127.0.0.1",18567));listener.listen(1)
    sender=socket.socket();sender.connect(("127.0.0.1",18567));receiver,_=listener.accept()
    receiver.setblocking(False)
    poll=select.poll();poll.register(receiver,select.POLLIN)
    print("SYSTEM_EXPORT "+json.dumps({"path":"select.poll","members":[[name,type(getattr(poll,name)).__name__,callable(getattr(poll,name))]for name in dir(poll)if not name.startswith("_")]}))
    sender.sendall(b"SELECT")
    result("select.select",lambda:len(select.select([receiver],[],[],1)[0]),lambda value:value==1,"actual guest TCP payload makes receiver readable")
    result("select.poll",lambda:len(poll.poll(1000)),lambda value:value==1,"native poll object detects actual guest TCP data")
    result("select.poll.register",lambda:len(poll.poll(1000)),lambda value:value==1,"registered socket receives actual readiness event")
    poll.modify(receiver,select.POLLIN|select.POLLOUT)
    result("select.poll.modify",lambda:any(mask&select.POLLIN for _,mask in poll.poll(1000)),lambda value:value,"modified event mask retains actual pending payload readability")
    result("select.poll.poll",lambda:len(poll.poll(1000)),lambda value:value==1,"actual TCP endpoint readiness reported")
    result("select.poll.ipoll",lambda:[[stream is receiver,mask]for stream,mask in poll.ipoll(1000)],lambda value:len(value)==1 and value[0][0],"iterator yields actual TCP readiness event")
    poll.unregister(receiver)
    result("select.poll.unregister",lambda:len(poll.poll(0)),lambda value:value==0,"removed socket no longer appears despite unread actual bytes")
    receiver.close();sender.close();listener.close()


def utilities():
    def controlled_exit():
        try:sys.exit(17)
        except SystemExit as error:return error.args[0]
    result("sys.exit",controlled_exit,lambda value:value==17,"native exit control flow raises documented SystemExit code")
    def print_exception():
        output=io.StringIO()
        try:raise ValueError("owned-native-fixture")
        except ValueError as error:sys.print_exception(error,output)
        return output.getvalue()
    result("sys.print_exception",print_exception,lambda value:"ValueError: owned-native-fixture"in value,"native traceback formatter writes exact exception into independent StringIO")
    result("bluetooth.UUID",lambda:bytes(bluetooth.UUID(0x180f)).hex(),lambda value:value=="0f18","standard independent little-endian Bluetooth16-bit UUID vector")


for name,action in (("ram-vfs",filesystems),("flash-vfs",global_filesystem),("readiness",readiness),("utilities",utilities)):
    try:action()
    except Exception as error:print("SYSTEM_API "+json.dumps({"api":"runtime."+name,"status":"ERROR","error":repr(error)}))
print("SYSTEM_RUNTIME_DONE")
