import Darwin
import Foundation
@preconcurrency import Virtualization

let arguments = CommandLine.arguments
guard arguments.count == 7, let incarnation = UUID(uuidString: arguments[5]),
      let volumeFD = Int32(arguments[6]), volumeFD >= 3 else { exit(64) }
let root = URL(fileURLWithPath: arguments[1], isDirectory: true)
let pinned = URL(fileURLWithPath: arguments[2], isDirectory: true)
let python = URL(fileURLWithPath: arguments[3])
let transportDir = URL(fileURLWithPath: arguments[4], isDirectory: true)
let runID = incarnation.uuidString.lowercased()
let streamPort: UInt32 = 18194
let egressPorts: [UInt32] = [18197, 18198]
umask(0o077)
signal(SIGPIPE, SIG_IGN)

func emit(_ event: String) {
    let line = Data("M5VZ_EVENT \(event) \(runID)\n".utf8)
    try? FileHandle.standardOutput.write(contentsOf: line)
}

var anchoredVolume = stat(), sharedVolume = stat(), socketDirectory = stat()
guard fstat(volumeFD, &anchoredVolume) == 0,
      lstat(root.appendingPathComponent("results").path, &sharedVolume) == 0,
      anchoredVolume.st_dev == sharedVolume.st_dev, anchoredVolume.st_ino == sharedVolume.st_ino,
      (sharedVolume.st_mode & S_IFMT) == S_IFDIR, sharedVolume.st_uid == getuid(),
      (sharedVolume.st_mode & 0o077) == 0, flock(volumeFD, LOCK_EX | LOCK_NB) == 0,
      fcntl(volumeFD, F_SETFD, FD_CLOEXEC) == 0,
      lstat(transportDir.path, &socketDirectory) == 0,
      (socketDirectory.st_mode & S_IFMT) == S_IFDIR, socketDirectory.st_uid == getuid(),
      (socketDirectory.st_mode & 0o777) == 0o700 else { exit(68) }

func privateOutput(_ name: String) -> FileHandle {
    let path = root.appendingPathComponent(name)
    let fd = open(path.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard fd >= 0 else { exit(65) }
    return FileHandle(fileDescriptor: fd, closeOnDealloc: true)
}

final class RelayListener: NSObject, VZVirtioSocketListenerDelegate {
    let protocolName: String
    let python: URL
    let root: URL
    let log: FileHandle
    var admitted = 0
    var children: [Process] = []

    init(_ protocolName: String, _ python: URL, _ root: URL, _ log: FileHandle) {
        self.protocolName = protocolName
        self.python = python
        self.root = root
        self.log = log
    }

    func listener(_ listener: VZVirtioSocketListener, shouldAcceptNewConnection connection: VZVirtioSocketConnection,
                  from socketDevice: VZVirtioSocketDevice) -> Bool {
        children.removeAll { !$0.isRunning }
        guard admitted < 32 && children.count < 2 else { return false }
        let fd = fcntl(connection.fileDescriptor, F_DUPFD_CLOEXEC, 3)
        guard fd >= 0 else { return false }
        let stream = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        let child = Process()
        child.executableURL = python
        child.arguments = ["-B", root.appendingPathComponent("host-relay.py").path, protocolName,
                           root.appendingPathComponent("scenarios/egress.private.json").path]
        child.standardInput = stream
        child.standardOutput = FileHandle.nullDevice
        child.standardError = log
        child.terminationHandler = { [connection, stream] _ in
            withExtendedLifetime(connection) { try? stream.close() }
        }
        do { try child.run() } catch { return false }
        admitted += 1
        children.append(child)
        return true
    }

    func retire() {
        for child in children where child.isRunning { child.terminate() }
        let deadline = Date().addingTimeInterval(2)
        while children.contains(where: { $0.isRunning }) && Date() < deadline { usleep(10_000) }
        for child in children where child.isRunning { Darwin.kill(child.processIdentifier, SIGKILL) }
        for child in children where child.isRunning { child.waitUntilExit() }
        children.removeAll()
    }
}

func unixListener(_ url: URL) -> Int32 {
    var address = sockaddr_un()
    let bytes = Array(url.path.utf8)
    let capacity = MemoryLayout.size(ofValue: address.sun_path)
    guard !bytes.contains(0), bytes.count < capacity else { return -1 }
    address.sun_family = sa_family_t(AF_UNIX)
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    withUnsafeMutableBytes(of: &address.sun_path) { target in
        bytes.withUnsafeBytes { target.copyMemory(from: $0) }
    }
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { return -1 }
    _ = fcntl(fd, F_SETFD, FD_CLOEXEC)
    let bound = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) == 0
        }
    }
    guard bound && chmod(url.path, 0o600) == 0 && listen(fd, 8) == 0 else {
        Darwin.close(fd)
        return -1
    }
    return fd
}

func applyTimeout(_ fd: Int32) {
    var timeout = timeval(tv_sec: 60, tv_usec: 0)
    let size = socklen_t(MemoryLayout<timeval>.size)
    _ = setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, size)
    _ = setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, size)
}

func pump(_ source: Int32, _ target: Int32) -> Bool {
    var buffer = [UInt8](repeating: 0, count: 32 * 1024)
    var remaining = 100 * 1024 * 1024
    while true {
        let count = Darwin.read(source, &buffer, buffer.count)
        if count < 0 && errno == EINTR { continue }
        if count == 0 {
            _ = Darwin.shutdown(target, SHUT_WR)
            return true
        }
        guard count > 0, count <= remaining else { return false }
        remaining -= count
        let sent = buffer.withUnsafeBytes { bytes -> Bool in
            guard let base = bytes.baseAddress else { return false }
            var offset = 0
            while offset < count {
                let size = Darwin.write(target, base.advanced(by: offset), count - offset)
                if size < 0 && errno == EINTR { continue }
                guard size > 0 else { return false }
                offset += size
            }
            return true
        }
        guard sent else { return false }
    }
}

final class Stream: @unchecked Sendable {
    let client: Int32
    private let lock = NSLock()
    private var peer: Int32?
    private var stopped = false
    private var closed = false

    init(_ client: Int32) {
        self.client = client
    }

    func attach(_ fd: Int32) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !closed && !stopped else { return false }
        peer = fd
        return true
    }

    func cancel() {
        lock.lock()
        defer { lock.unlock() }
        guard !closed && !stopped else { return }
        stopped = true
        _ = Darwin.shutdown(client, SHUT_RDWR)
        if let peer { _ = Darwin.shutdown(peer, SHUT_RDWR) }
    }

    func finish() {
        lock.lock()
        defer { lock.unlock() }
        guard !closed else { return }
        closed = true
        Darwin.close(client)
    }
}

final class Transport: @unchecked Sendable {
    let socketURL: URL
    let listener: Int32
    let work = DispatchQueue(label: "m5-vz-accept")
    // All membership transitions happen on the VZ/main queue.
    var streams: [Int32: Stream] = [:]
    var running = false
    var socketDevice: VZVirtioSocketDevice?

    init?(_ socketURL: URL) {
        self.socketURL = socketURL
        let fd = unixListener(socketURL)
        guard fd >= 0 else { return nil }
        listener = fd
    }

    func start(_ device: VZVirtioSocketDevice) {
        socketDevice = device
        running = true
        work.async { [self] in
            while true {
                let accepted = Darwin.accept(listener, nil, nil)
                if accepted < 0 && errno == EINTR { continue }
                if accepted < 0 { return }
                guard fcntl(accepted, F_SETFD, FD_CLOEXEC) == 0 else {
                    Darwin.close(accepted)
                    continue
                }
                applyTimeout(accepted)
                DispatchQueue.main.sync {
                    guard let device = socketDevice else { Darwin.close(accepted); return }
                    attach(accepted, device)
                }
            }
        }
    }

    func attach(_ fd: Int32, _ device: VZVirtioSocketDevice) {
        guard running && streams.count < 8 else { Darwin.close(fd); return }
        let stream = Stream(fd)
        streams[fd] = stream
        DispatchQueue.global().asyncAfter(deadline: .now() + .seconds(180)) { stream.cancel() }
        device.connect(toPort: streamPort) { [self] result in
            guard case .success(let connection) = result, stream.attach(connection.fileDescriptor) else {
                complete(stream)
                return
            }
            let peer = connection.fileDescriptor
            applyTimeout(peer)
            let group = DispatchGroup()
            group.enter()
            DispatchQueue.global().async {
                if !pump(fd, peer) { stream.cancel() }
                group.leave()
            }
            group.enter()
            DispatchQueue.global().async {
                if !pump(peer, fd) { stream.cancel() }
                group.leave()
            }
            group.notify(queue: .main) {
                withExtendedLifetime(connection) { self.complete(stream) }
            }
        }
    }

    func complete(_ stream: Stream) {
        streams.removeValue(forKey: stream.client)
        stream.finish()
    }

    func retire() {
        running = false
        socketDevice = nil
        _ = Darwin.shutdown(listener, SHUT_RDWR)
        Darwin.close(listener)
        unlink(socketURL.path)
        for stream in streams.values { stream.cancel() }
    }
}

let serialOut = privateOutput("serial-\(runID).private.log")
let relayOut = privateOutput("relay-\(runID).private.log")
let config = VZVirtualMachineConfiguration()
config.platform = VZGenericPlatformConfiguration()
config.cpuCount = 1
config.memorySize = 1536 * 1024 * 1024
config.networkDevices = []
config.storageDevices = []
config.socketDevices = [VZVirtioSocketDeviceConfiguration()]
let boot = VZLinuxBootLoader(kernelURL: pinned.appendingPathComponent("cloud-kernel"))
boot.initialRamdiskURL = root.appendingPathComponent("vsock-initrd.img")
boot.commandLine = "console=hvc0 rdinit=/m5vz-vsock-init loglevel=5"
config.bootLoader = boot
let serial = VZVirtioConsoleDeviceSerialPortConfiguration()
serial.attachment = VZFileHandleSerialPortAttachment(fileHandleForReading: nil, fileHandleForWriting: serialOut)
config.serialPorts = [serial]
func share(_ tag: String, _ path: URL, _ readOnly: Bool) -> VZVirtioFileSystemDeviceConfiguration {
    let device = VZVirtioFileSystemDeviceConfiguration(tag: tag)
    device.share = VZSingleDirectoryShare(directory: VZSharedDirectory(url: path, readOnly: readOnly))
    return device
}
config.directorySharingDevices = [
    share("labshare", pinned.appendingPathComponent("readonly-share"), true),
    share("labscenario", root.appendingPathComponent("scenarios"), true),
    share("labresults", root.appendingPathComponent("results"), false),
]
do { try config.validate() } catch { emit("invalid-configuration"); exit(66) }
func makeTransport() -> Transport {
    guard let result = Transport(transportDir.appendingPathComponent("d")) else { exit(66) }
    return result
}
let transport = makeTransport()

let vm = VZVirtualMachine(configuration: config)
let egress = [
    RelayListener("sntp", python, root, relayOut),
    RelayListener("voice", python, root, relayOut),
]
let relaySockets = egress.map { delegate in
    let socket = VZVirtioSocketListener()
    socket.delegate = delegate
    return socket
}

var hasRetired = false
func retire() {
    guard !hasRetired else { return }
    hasRetired = true
    transport.retire()
    if let socketDevice = vm.socketDevices.first as? VZVirtioSocketDevice {
        for port in egressPorts { socketDevice.removeSocketListener(forPort: port) }
    }
    for listener in egress { listener.retire() }
}

final class VMDelegate: NSObject, VZVirtualMachineDelegate {
    func guestDidStop(_ virtualMachine: VZVirtualMachine) {
        retire()
        emit("guest-stopped")
        exit(0)
    }

    func virtualMachine(_ virtualMachine: VZVirtualMachine, didStopWithError error: Error) {
        retire()
        emit("vz-error")
        exit(67)
    }
}

let delegate = VMDelegate()
vm.delegate = delegate
var forced = false
signal(SIGUSR1, SIG_IGN)
let force = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
force.setEventHandler {
    guard !forced else { return }
    forced = true
    retire()
    guard vm.canStop else { emit("force-unconfirmed"); exit(69) }
    vm.stop { error in
        guard error == nil else { emit("force-unconfirmed"); exit(69) }
        emit("forced-stop-ack")
        exit(70)
    }
}
force.resume()
vm.start { result in
    guard case .success = result, let device = vm.socketDevices.first as? VZVirtioSocketDevice else {
        retire()
        emit("vz-start-failed")
        exit(66)
    }
    if FileManager.default.fileExists(atPath: root.appendingPathComponent("scenarios/egress.private.json").path) {
        guard FileManager.default.fileExists(atPath: root.appendingPathComponent("host-relay.py").path) else {
            emit("missing-fixed-egress"); kill(getpid(), SIGUSR1); return
        }
        for (port, socket) in zip(egressPorts, relaySockets) { device.setSocketListener(socket, forPort: port) }
    }
    transport.start(device)
    emit("started")
}
withExtendedLifetime((vm, delegate, force, egress, relaySockets, serialOut, relayOut)) { dispatchMain() }
