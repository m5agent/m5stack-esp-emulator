"""Ordinary Plus methods; host HTTP acknowledgements bind each retained frame."""
import json
import time
import os
import M5
from M5 import Widgets
import requests

if globals().get("PLUS_CANDIDATE"):
    from candidate_label_plus import LabelPlus
else:
    from label_plus import LabelPlus
from image_plus import ImagePlus

BACKGROUND = 0x0B1014
keep = []


def settle():
    for _ in range(20):
        M5.update()
        time.sleep_ms(20)


def record(target, method, status, **details):
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target=target, method=method, status=status, **details)))


def capture(phase):
    settle()
    print("M5EMU_PLUS_PHASE " + phase)
    response = requests.get(TEST_BASE_URL + "/phase/" + phase)
    try:
        assert response.status_code == 200, "host frame acknowledgement failed"
    finally:
        response.close()


def clear():
    for obj in keep:
        obj.setVisible(False)
    Widgets.fillScreen(BACKGROUND)


def label_case(method):
    clear()
    try:
        obj = LabelPlus("Initial", 30 if method == "setCursor" else 10,
                        75 if method == "setCursor" else 10, 1.0,
                        0xFFFFFF, BACKGROUND, Widgets.FONTS.DejaVu18,
                        TEST_BASE_URL + "/label", 0, False, "value", "ERROR")
    except Exception as error:
        record("label_plus.LabelPlus", method, "BLOCKED_CONSTRUCTOR", error=repr(error),
               oracle="this exact Plus constructor must succeed before its ordinary method can run")
        return
    keep.append(obj)
    text = {"setText": "TEXT", "setCursor": "CURSOR", "setSize": "SIZE",
            "setFont": "FONT", "setVisible": "VISIBLE"}[method]
    if method != "setText":
        obj.setText(text)
    if method == "setVisible":
        capture("label_setVisible_before")
        obj.setVisible(False)
    elif method == "setText":
        obj.setText(text)
    elif method == "setCursor":
        obj.setCursor(10, 10)
    elif method == "setSize":
        obj.setSize(1.5)
    elif method == "setFont":
        obj.setFont(Widgets.FONTS.DejaVu12)
    if method != "setVisible":
        control = Widgets.Label(text, 130, 10, 1.5 if method == "setSize" else 1.0,
                                0xFFFFFF, BACKGROUND,
                                Widgets.FONTS.DejaVu12 if method == "setFont" else Widgets.FONTS.DejaVu18)
        keep.append(control)
    record("label_plus.LabelPlus", method, "CALL_OK",
           oracle="actual method on an HTTP-backed Plus object; separate retained frame checks its effect")
    capture("label_" + method)
    obj.deinit()


def image_case(method):
    clear()
    try:
        obj = ImagePlus(TEST_BASE_URL + "/fixture.png",
                        170 if method == "setCursor" else 10,
                        90 if method == "setCursor" else 10,
                        False, 60000, default_img="/flash/res/img/plus-fixture.png")
    except Exception as error:
        record("image_plus.ImagePlus", method, "BLOCKED_CONSTRUCTOR", error=repr(error),
               oracle="this exact Plus constructor must succeed before its ordinary method can run")
        return
    keep.append(obj)
    with open("/flash/res/img/fixture.png", "rb") as downloaded:
        actual = downloaded.read()
    with open("/flash/fixture.png", "rb") as expected:
        reference = expected.read()
    print("M5EMU_PLUS_IMAGE_FIXTURE " + json.dumps(dict(
        method=method, downloaded_bytes=len(actual), reference_bytes=len(reference),
        exact_download=actual == reference, valid=obj.is_valid_image())))
    # Separate native controls diagnose PNG/VFS versus Plus mutation failures.
    # They never grant a Plus method PASS.
    control = Widgets.Image("/flash/res/img/fixture.png", 80, 70)
    keep.append(control)
    if method == "setCursor":
        obj.setCursor(10, 10)
    elif method == "setImage":
        obj.setImage("/flash/fixture-alt.png")
    elif method == "setScale":
        obj.setScale(2.0, 2.0)
    elif method == "setVisible":
        capture("image_setVisible_before")
        obj.setVisible(False)
    record("image_plus.ImagePlus", method, "CALL_OK",
           oracle="actual method on an HTTP-backed Plus object; separate retained frame checks its effect")
    capture("image_" + method)
    obj.deinit()


try:
    M5.begin()
    connect_wifi()
    Widgets.setRotation(1)
    for directory in ("/flash/res", "/flash/res/img"):
        try:
            os.mkdir(directory)
        except OSError:
            pass
    for method in ("setText", "setCursor", "setSize", "setFont", "setVisible"):
        try:
            label_case(method)
        except Exception as error:
            record("label_plus.LabelPlus", method, "FAIL", error=repr(error))
    for method in ("setCursor", "setImage", "setScale", "setVisible"):
        try:
            image_case(method)
        except Exception as error:
            record("image_plus.ImagePlus", method, "FAIL", error=repr(error))
except Exception as error:
    record("plus.methods", "fixture", "FIXTURE_ERROR", error=repr(error))
print("PLUS_METHODS_DONE")
