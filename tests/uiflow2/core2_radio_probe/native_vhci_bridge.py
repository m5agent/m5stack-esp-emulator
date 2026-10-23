"""Bridge stock Core2 VHCI traffic to an external Bumble HCI controller."""
from __future__ import annotations

import os
import queue
import socket
import threading
import time

import gdb
from hci_stream import HciStreamParser

VHCI_ENV_POINTER = 0x3FFCC0A4
VHCI_CALLBACK_OFFSET = 0x4E4
API_SEND_PACKET = 0x403064D8
IDLE_FUNCTION = "esp_cpu_wait_for_intr"
INJECTION_BUFFER_SIZE = 4096


def _read_u32(address: int) -> int:
    inferior = gdb.selected_inferior()
    return int.from_bytes(inferior.read_memory(address, 4).tobytes(), "little")


class NativeVhciBridge:
    def __init__(self, port: int) -> None:
        self.port = port
        self.condition = threading.Condition()
        self.pending: queue.Queue[bytes] = queue.Queue()
        self.socket = self._connect(port)
        self.injection_buffer = 0
        self.idle_breakpoint: gdb.Breakpoint | None = None
        self.injecting = False
        self.stopping = False
        threads = gdb.selected_inferior().threads()
        if not threads:
            raise RuntimeError("no guest threads available for VHCI bridge")
        self.injection_thread = min(threads, key=lambda thread: thread.num)
        self.reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader.start()
        self.send_breakpoint = SendPacketBreakpoint(self)

    @staticmethod
    def _connect(port: int) -> socket.socket:
        deadline = time.monotonic() + 10
        while True:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=2)
                sock.settimeout(None)
                return sock
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def _reader_loop(self) -> None:
        parser = HciStreamParser()
        while not self.stopping:
            try:
                data = self.socket.recv(4096)
            except OSError:
                break
            if not data:
                break
            try:
                packets = parser.feed(data)
            except Exception as error:
                print(f"NATIVE_VHCI_PARSE_ERROR {error!r}", flush=True)
                break
            for packet in packets:
                print(f"NATIVE_VHCI_C2H {packet.hex()}", flush=True)
                self.pending.put(packet)
                with self.condition:
                    self.condition.notify_all()

    def _ensure_buffer(self) -> int:
        if not self.injection_buffer:
            self.injection_thread.switch()
            value = gdb.parse_and_eval(
                f"((void *(*)(unsigned int))malloc)({INJECTION_BUFFER_SIZE})"
            )
            self.injection_buffer = int(value)
            if not self.injection_buffer:
                raise RuntimeError("guest malloc failed for VHCI injection buffer")
            print(
                f"NATIVE_VHCI_BUFFER 0x{self.injection_buffer:08x}",
                flush=True,
            )
        return self.injection_buffer

    def _callbacks(self) -> tuple[int, int]:
        env = _read_u32(VHCI_ENV_POINTER)
        if not env:
            raise RuntimeError("VHCI environment is not initialized")
        callback = _read_u32(env + VHCI_CALLBACK_OFFSET)
        if not callback:
            raise RuntimeError("VHCI host callback is not registered")
        send_available = _read_u32(callback)
        receive = _read_u32(callback + 4)
        if not send_available or not receive:
            raise RuntimeError("VHCI callback table is incomplete")
        return send_available, receive

    def _inject(self, packet: bytes) -> None:
        buffer = self._ensure_buffer()
        inferior = gdb.selected_inferior()
        inferior.write_memory(buffer, packet)
        _, receive = self._callbacks()
        self.injecting = True
        self.injection_thread.switch()
        try:
            result = gdb.parse_and_eval(
                "((int (*)(unsigned char *, unsigned short))"
                f"{receive})((unsigned char *){buffer}, {len(packet)})"
            )
            if int(result) != 0:
                print(
                    f"NATIVE_VHCI_INJECT_REJECTED status={int(result)} "
                    f"packet={packet.hex()}",
                    flush=True,
                )
        finally:
            self.injecting = False

    def drain_pending(self) -> int:
        count = 0
        while True:
            try:
                packet = self.pending.get_nowait()
            except queue.Empty:
                break
            self._inject(packet)
            count += 1
        if count:
            send_available, _ = self._callbacks()
            gdb.parse_and_eval(f"((void (*)()){send_available})()")
        return count

    def wait_and_inject(self, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.pending.empty():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return 0
                self.condition.wait(remaining)
        time.sleep(0.02)
        return self.drain_pending()

    def arm_idle_wait(self, timeout: float = 20.0) -> None:
        self.disarm_idle_wait()
        self.idle_breakpoint = IdleBreakpoint(self, timeout=timeout)

    def disarm_idle_wait(self) -> None:
        if self.idle_breakpoint is not None:
            try:
                self.idle_breakpoint.delete()
            except Exception:
                pass
            self.idle_breakpoint = None

    def close(self) -> None:
        self.stopping = True
        self.disarm_idle_wait()
        try:
            self.socket.close()
        except OSError:
            pass


class SendPacketBreakpoint(gdb.Breakpoint):
    def __init__(self, bridge: NativeVhciBridge) -> None:
        super().__init__(f"*{API_SEND_PACKET}", internal=True)
        self.bridge = bridge

    def stop(self) -> bool:
        data_pointer = int(gdb.parse_and_eval("$a2"))
        data_length = int(gdb.parse_and_eval("$a3")) & 0xFFFF
        packet = bytes(
            gdb.selected_inferior().read_memory(data_pointer, data_length)
        )
        print(f"NATIVE_VHCI_H2C {packet.hex()}", flush=True)
        self.bridge.disarm_idle_wait()
        self.bridge.socket.sendall(packet)
        try:
            gdb.execute("return", to_string=True)
        except gdb.error as error:
            print(f"NATIVE_VHCI_RETURN_ERROR {error}", flush=True)
            return True
        self.bridge.wait_and_inject(timeout=2.0)
        self.bridge.arm_idle_wait()
        return False


class IdleBreakpoint(gdb.Breakpoint):
    def __init__(self, bridge: NativeVhciBridge, timeout: float) -> None:
        super().__init__(IDLE_FUNCTION, internal=True)
        self.bridge = bridge
        self.timeout = timeout

    def stop(self) -> bool:
        if self.bridge.injecting:
            return False
        self.enabled = False
        print("NATIVE_VHCI_IDLE_WAIT", flush=True)
        injected = self.bridge.wait_and_inject(self.timeout)
        print(f"NATIVE_VHCI_IDLE_INJECTED {injected}", flush=True)
        self.bridge.idle_breakpoint = None
        return False


_bridge: NativeVhciBridge | None = None


def start() -> None:
    global _bridge
    port = int(os.environ["M5_NATIVE_BT_HCI_PORT"])
    gdb_port = int(os.environ["M5_NATIVE_GDB_PORT"])
    gdb.execute("set confirm off")
    gdb.execute(f"target remote :{gdb_port}")
    _bridge = NativeVhciBridge(port)
    print("NATIVE_VHCI_BRIDGE_READY", flush=True)


def stop() -> None:
    global _bridge
    if _bridge is not None:
        _bridge.close()
        _bridge = None
