import os, sys, io
import M5
from M5 import *
from module import DualKmeterModule



label0 = None
km_0 = None


def setup():
  global label0, km_0

  M5.begin()
  Widgets.setRotation(0)
  Widgets.fillScreen(0x222222)
  label0 = Widgets.Label("Text", 2, 34, 1.0, 0xffffff, 0x222222, Widgets.FONTS.Montserrat18)

  km_0 = DualKmeterModule(address=0x11)


def loop():
  global label0, km_0
  M5.update()
  if km_0.is_ready():
    label0.setText(str(km_0.get_thermocouple_temperature(scale=km_0.CELSIUS)))


if __name__ == '__main__':
  try:
    setup()
    while True:
      loop()
  except (Exception, KeyboardInterrupt) as e:
    try:
      from utility import print_error_msg
      print_error_msg(e)
    except ImportError:
      print("please update to latest firmware")
