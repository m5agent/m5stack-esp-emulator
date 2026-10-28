"""Native image/QR/JPEG tests on a real camera-returned image.

Known pixel inputs are written using public image APIs. The result proves
image processing and memory behavior; it does not claim optical/RF/hardware
measurements. Each return-object accessor has its own behavioral oracle.
"""
import json
import time
import M5


def emit(api, passed, **details):
    details.update(api=api, status="PASS" if passed else "FAIL")
    print("VISION_API " + json.dumps(details))


def reflect(path, obj):
    names = [name for name in dir(obj) if not name.startswith("_")]
    print("VISION_EXPORT " + json.dumps({"path": path, "members": names, "type_name": type(obj).__name__}))


def run():
    modules = {}
    for name in ("camera", "image", "jpg", "code_scanner", "dl", "usb", "usb.device", "usb.device.keyboard", "usb.device.mouse"):
        try:
            obj = __import__(name, None, None, ["*"])
            modules[name] = obj
            reflect(name, obj)
        except ImportError as error:
            print("VISION_EXPORT " + json.dumps({"path": name, "status": "UNAVAILABLE_ON_DEVICE", "error": repr(error)}))
    if "camera" not in modules or "image" not in modules:
        return
    camera, image = modules["camera"], modules["image"]
    M5.begin()
    camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    img = camera.snapshot()
    emit("camera.snapshot", img is not None, input="controller-generated QVGA RGB565 scene")
    if img is None:
        return
    reflect("image.Image", img)
    width, height = img.width(), img.height()
    emit("image.Image.width", width == 320, value=width)
    emit("image.Image.height", height == 240, value=height)
    emit("image.Image.size", img.size() == width * height * 2, value=img.size())
    emit("image.Image.format", img.format() == image.RGB565, value=img.format())
    pixels = img.bytearray()
    def pixel(x, y):
        offset = (y * width + x) * 2
        return pixels[offset] | pixels[offset + 1] << 8
    original = pixels[0]
    pixels[0] ^= 0xff
    emit("image.Image.bytearray", img.bytearray()[0] == (original ^ 0xff), oracle="shared mutable image storage")
    img.clear()
    emit("image.Image.clear", not any(pixels), oracle="all image bytes zero")
    cases = [
        ("draw_line", lambda: img.draw_line(10, 10, 40, 10, color=(255, 255, 255), thickness=1), lambda: pixel(20, 10) == 65535 and pixel(20, 20) == 0),
        ("draw_rectangle", lambda: img.draw_rectangle(10, 10, 30, 30, color=(255, 255, 255), fill=True), lambda: pixel(20, 20) == 65535 and pixel(80, 80) == 0),
        ("draw_circle", lambda: img.draw_circle(30, 30, 10, color=(255, 255, 255), fill=True), lambda: pixel(30, 30) == 65535 and pixel(60, 60) == 0),
        ("draw_string", lambda: img.draw_string(10, 10, "ABC", color=(255, 255, 255), scale=2), lambda: any(pixels[(10 * width) * 2:(45 * width) * 2]) and pixel(200, 200) == 0),
        ("draw_ellipse", lambda: img.draw_ellipse(30, 30, 12, 8, 0, color=(255, 255, 255), fill=True), lambda: pixel(30, 30) == 65535 and pixel(80, 80) == 0),
        ("draw_cross", lambda: img.draw_cross(30, 30, color=(255, 255, 255), size=8), lambda: pixel(30, 30) == 65535 and pixel(80, 80) == 0),
        ("draw_arrow", lambda: img.draw_arrow(10, 10, 50, 10, color=(255, 255, 255)), lambda: pixel(25, 10) == 65535 and pixel(80, 80) == 0),
        ("draw_edges", lambda: img.draw_edges([(10, 10), (40, 10), (40, 40), (10, 40)], color=(255, 255, 255)), lambda: pixel(25, 10) == 65535 and pixel(80, 80) == 0),
    ]
    for name, action, oracle in cases:
        img.clear()
        try:
            action()
            emit("image.Image." + name, oracle(), oracle="known foreground/background pixel locations")
        except Exception as error:
            emit("image.Image." + name, False, error=repr(error))
    with open("/flash/qr.json") as handle:
        fixture = json.load(handle)
    img.draw_rectangle(0, 0, width, height, color=(255, 255, 255), fill=True)
    rows, scale, left, top = fixture["rows"], 6, 58, 18
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value == "1":
                img.draw_rectangle(left + x * scale, top + y * scale, scale, scale, color=(0, 0, 0), fill=True)
    for scanner_name, scan in [("image.Image.find_qrcodes", lambda: img.find_qrcodes()),
                               ("code_scanner.find_qrcodes", lambda: modules["code_scanner"].find_qrcodes(img))]:
        try:
            result = scan()
            found = result[0] if isinstance(result, (list, tuple)) and result else result
            emit(scanner_name, bool(found) and found.payload() == fixture["payload"], payload=found.payload() if found else None)
            if not found:
                continue
            reflect(scanner_name + ".result", found)
            for method in ("payload", "type_name", "corners", "rect", "x", "y", "w", "h", "version", "ecc_level", "mask", "eci"):
                if not hasattr(found, method):
                    continue
                value = getattr(found, method)()
                if method == "payload":
                    ok = value == fixture["payload"]
                elif method == "corners":
                    ok = len(value) == 4 and all(58 <= p[0] <= 256 and 18 <= p[1] <= 216 for p in value)
                elif method == "rect":
                    ok = len(value) == 4 and value[2] > 100 and value[3] > 100
                elif method in ("x", "y"):
                    ok = 18 <= value <= 100
                elif method in ("w", "h"):
                    ok = 100 <= value <= 200
                elif method == "version":
                    ok = value == 2
                elif method == "mask":
                    ok = 0 <= value <= 7
                elif method == "eci":
                    ok = value == 0
                elif method == "ecc_level":
                    ok = value in (0, 1)
                else:
                    ok = "QR" in str(value).upper()
                emit(scanner_name + ".result." + method, ok, value=value)
        except Exception as error:
            emit(scanner_name, False, error=repr(error))
    if "jpg" in modules:
        try:
            jpg = modules["jpg"]
            encoded = jpg.encode(img, 80)
            data = encoded.bytearray()
            emit("jpg.encode", encoded.format() == image.JPEG and bytes(data[:2]) == b"\xff\xd8", bytes=len(data))
            print("VISION_JPEG_HEX " + bytes(data).hex())
            decoded = jpg.decode(encoded)
            decoded_codes = decoded.find_qrcodes()
            survived = bool(decoded_codes) and decoded_codes[0].payload() == fixture["payload"]
            emit("jpg.decode", survived and decoded.format() == image.RGB565 and decoded.width() == width and decoded.height() == height, size=decoded.size(), oracle="known QR payload survives actual JPEG encode/decode")
            try:
                with open("/flash/host-reencoded.jpg", "rb") as handle:
                    alternate = handle.read()
            except OSError:
                alternate = None
            if alternate is not None and len(alternate) <= len(data):
                data[:len(alternate)] = alternate
                data[len(alternate):] = b"\x00" * (len(data) - len(alternate))
                alternate_image = jpg.decode(encoded)
                alternate_codes = alternate_image.find_qrcodes()
                emit("jpg.decode.host_fixture", bool(alternate_codes) and alternate_codes[0].payload() == fixture["payload"], oracle="independent Pillow encoder input with the same known QR")
        except Exception as error:
            emit("jpg.roundtrip", False, error=repr(error))
    M5.Display.show(img, 0, 0)
    camera.deinit()


try:
    run()
except Exception as error:
    print("VISION_API " + json.dumps({"api": "vision.run", "status": "ERROR", "error": repr(error)}))
print("VISION_API_DONE")
