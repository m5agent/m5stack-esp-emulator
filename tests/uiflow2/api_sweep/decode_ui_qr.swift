import Foundation
import Vision

if CommandLine.arguments.count != 2 {
    fputs("usage: decode_ui_qr PNG\n", stderr)
    exit(2)
}
let request = VNDetectBarcodesRequest()
request.symbologies = [.qr]
let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
do {
    try handler.perform([request])
    let messages = (request.results ?? []).compactMap { $0.payloadStringValue }
    let data = try JSONSerialization.data(withJSONObject: messages)
    FileHandle.standardOutput.write(data)
} catch {
    fputs("QR decoder failed\n", stderr)
    exit(1)
}
