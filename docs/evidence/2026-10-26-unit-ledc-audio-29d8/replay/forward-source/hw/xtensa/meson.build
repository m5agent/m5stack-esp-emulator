xtensa_ss = ss.source_set()
xtensa_ss.add(files(
  'mx_pic.c',
  'pic_cpu.c',
  'xtensa_memory.c',
  '../m5stopwatch/m5_board.c',
  '../m5stopwatch/m5_unit_runtime.c',
  '../m5stopwatch/m5_unit_gpio.c',
  '../m5stopwatch/esp32s3_sens.c',
  '../m5stopwatch/m5_unit_i2c_sensors.c',
  '../m5stopwatch/m5_unit_i2c_controls.c',
  '../m5stopwatch/m5_can_peer.c',
  '../m5stopwatch/m5_rmt.c',
  '../m5stopwatch/m5_scs_servo.c',
  '../m5stopwatch/m5_st25r3916_spi.c',
  '../m5stopwatch/m5_cc1101_spi.c',
  '../m5stopwatch/m5_uart_peer.c',
  '../m5stopwatch/m5_sx1262.c',
  '../m5stopwatch/m5_spi_sd.c',
  '../m5stopwatch/m5_max3421e.c',
  '../m5stopwatch/m5_spi_panel.c',
  '../m5stopwatch/m5sw_i2c_devs.c',
  '../m5stopwatch/esp32s3_soft_i2c.c',
))
xtensa_ss.add(when: 'CONFIG_XTENSA_SIM', if_true: files('sim.c'))
xtensa_ss.add(when: 'CONFIG_XTENSA_VIRT', if_true: files('virt.c'))
xtensa_ss.add(when: 'CONFIG_XTENSA_XTFPGA', if_true: files('xtfpga.c'))
xtensa_ss.add(when: 'CONFIG_XTENSA_ESP32', if_true: files(
  'esp32.c',
  'esp32_intc.c',
  'esp32_native_hci.c',
  '../m5stopwatch/m5core2.c',
  '../m5stopwatch/m5_i2s_esp32.c',
))
xtensa_ss.add(when: 'CONFIG_XTENSA_ESP32S3', if_true: files(
  'esp32s3_clk.c',
  'esp32s3_intc.c',
  'esp32s3.c',
  '../m5stopwatch/esp32s3_i2c.c',
  '../m5stopwatch/esp32s3_gpspi.c',
  '../m5stopwatch/esp32s3_regi2c.c',
  '../m5stopwatch/esp32s3_fe.c',
  '../m5stopwatch/esp32s3_phy.c',
  '../m5stopwatch/co5300.c',
  '../m5stopwatch/m5sticks3.c',
  '../m5stopwatch/m5atoms3r.c',
  '../m5stopwatch/m5cores3.c',
  '../m5stopwatch/m5cardputeradv.c',
  '../m5stopwatch/m5stamplc.c',
  '../m5stopwatch/m5stackchan.c',
  '../m5stopwatch/m5_epd_panel.c',
  '../m5stopwatch/m5_lcd_cam.c',
  '../m5stopwatch/m5_i2s.c',
  '../m5stopwatch/m5papermono.c',
  '../m5stopwatch/m5papercolor.c',
))

hw_arch += {'xtensa': xtensa_ss}
