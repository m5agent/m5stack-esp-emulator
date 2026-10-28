"""Native ESP-DL against official example pixels and an all-black control.

Inputs use the public image bytearray API after actual controller capture;
this tests inference, result accessors and recognizer state, not optics.
"""
import json
import hashlib
import M5


def emit(api, passed, **details):
    details.update(api=api, status="PASS" if passed else "FAIL")
    print("DL_API " + json.dumps(details))


def reflect(path, value):
    print("DL_EXPORT " + json.dumps({"path": path, "members": [x for x in dir(value) if not x.startswith("_")]}))


def run():
    try:
        import camera
        import image
        import dl
    except ImportError as error:
        print("DL_API " + json.dumps({"api": "dl", "status": "UNAVAILABLE_ON_DEVICE", "error": repr(error)}))
        return
    M5.begin()
    reflect("dl.model", dl.model)
    camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    img = camera.snapshot()
    if img is None:
        raise RuntimeError("camera did not return an image storage object")
    data = img.bytearray()
    face_keypoint = None
    face_pixels = None
    for fixture, model in (("face", dl.model.HUMAN_FACE_DETECT), ("pedestrian", dl.model.PEDESTRIAN_DETECT)):
        detector = dl.ObjectDetector(model)
        reflect("dl.ObjectDetector", detector)
        img.clear()
        negative_before = hashlib.sha256(data).digest().hex()
        negative_nonzero = sum(1 for value in data if value)
        negative = detector.infer(img)
        negative_after = hashlib.sha256(data).digest().hex()
        emit("dl.ObjectDetector.infer.negative", not negative and negative_nonzero == 0 and negative_before == negative_after, model=fixture, detections=len(negative) if negative else 0, before_sha256=negative_before, after_sha256=negative_after, nonzero=negative_nonzero)
        with open("/flash/" + fixture + ".rgb565", "rb") as handle:
            pixels = handle.read()
        if len(pixels) != len(data):
            raise ValueError("RGB565 fixture shape differs from real image storage")
        data[:] = pixels
        positive_before = hashlib.sha256(data).digest().hex()
        print("DL_INPUT " + json.dumps({"model": fixture, "fixture_sha256": hashlib.sha256(pixels).digest().hex(), "image_sha256": positive_before}))
        results = detector.infer(img)
        positive_after = hashlib.sha256(data).digest().hex()
        print("DL_INPUT_AFTER " + json.dumps({"model": fixture, "image_sha256": positive_after}))
        emit("dl.ObjectDetector", bool(results) and not negative, model=fixture, oracle="official positive image versus all-black negative")
        emit("dl.ObjectDetector.infer", bool(results) and not negative, model=fixture, detections=len(results) if results else 0)
        if not results:
            continue
        found = results[0]
        reflect("dl.DetectionResult", found)
        values = {method: getattr(found, method)() for method in ("bbox", "x", "y", "w", "h", "category", "keypoint", "score")}
        emit("dl.DetectionResult.bbox", len(values["bbox"]) == 4 and values["w"] > 0 and values["h"] > 0, model=fixture, value=values["bbox"])
        for method in ("x", "y", "w", "h"):
            limit = 320 if method in ("x", "w") else 240
            emit("dl.DetectionResult." + method, 0 <= values[method] <= limit, model=fixture, value=values[method])
        emit("dl.DetectionResult.category", isinstance(values["category"], int) and values["category"] >= 0, model=fixture, value=values["category"])
        emit("dl.DetectionResult.score", 0 <= values["score"] <= 1, model=fixture, value=values["score"])
        keypoint = values["keypoint"]
        emit("dl.DetectionResult.keypoint", (len(keypoint) == 10 and all(0 <= v <= 320 for v in keypoint)) if fixture == "face" else len(keypoint) == 10 and not any(keypoint), model=fixture, value=keypoint)
        if fixture == "face":
            face_keypoint, face_pixels = keypoint, pixels
    if face_keypoint is None:
        print("DL_API " + json.dumps({"api": "dl.HumanFaceRecognizer", "status": "BLOCKED_FIXTURE", "reason": "positive face detector did not produce required keypoints"}))
    else:
        data[:] = face_pixels
        recognizer = dl.HumanFaceRecognizer()
        reflect("dl.HumanFaceRecognizer", recognizer)
        recognizer.clear_id()
        emit("dl.HumanFaceRecognizer.clear_id", recognizer.enrolled_id_num() == 0)
        enrolled = recognizer.enroll_id(img, face_keypoint)
        count = recognizer.enrolled_id_num()
        emit("dl.HumanFaceRecognizer.enroll_id", bool(enrolled) and count == 1, value=enrolled, count=count)
        emit("dl.HumanFaceRecognizer.enrolled_id_num", count == 1, count=count)
        result = recognizer.recognize(img, face_keypoint)
        reflect("dl.RecognitionResult", result)
        identity, similarity = result.id(), result.similarity()
        emit("dl.HumanFaceRecognizer.recognize", identity > 0 and similarity > 0.9, identity=identity, similarity=similarity)
        emit("dl.RecognitionResult.id", identity > 0, value=identity)
        emit("dl.RecognitionResult.similarity", 0.9 < similarity <= 1.01, value=similarity)
        img.clear()
        negative_result = recognizer.recognize(img, face_keypoint)
        emit("dl.HumanFaceRecognizer.recognize.negative", negative_result.id() <= 0 or negative_result.similarity() < 0.8,
             identity=negative_result.id(), similarity=negative_result.similarity(),
             oracle="all-black input must not match the enrolled official face")
        recognizer.delete_id(identity)
        emit("dl.HumanFaceRecognizer.delete_id", recognizer.enrolled_id_num() == 0)
        recognizer.clear_id()
    camera.deinit()


try:
    run()
except Exception as error:
    print("DL_API " + json.dumps({"api": "dl.run", "status": "ERROR", "error": repr(error)}))
print("DL_API_DONE")
