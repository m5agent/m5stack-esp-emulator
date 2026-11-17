from time import sleep_ms
from u197_driver import AudioPlayerUnit
from probe_config import PORT, TRACKS

print("N9301_PROBE_BOOT", PORT, TRACKS)
driver = AudioPlayerUnit(2, PORT)
if TRACKS == 0:
    assert driver.check_play_status() == -1
    assert driver.get_current_online_device_type() == -1
    print("N9301_PROBE_NO_MEDIA")
else:
    assert driver.check_play_status() == 0
    assert driver.get_current_online_device_type() == 2
    assert driver.get_current_play_device_type() == 1
    assert driver.get_total_audio_number() == TRACKS
    assert driver.get_file_count() == TRACKS
    assert driver.get_volume() == 30
    assert driver.get_play_mode() == 4
    print("N9301_PROBE_MEDIA", TRACKS)
    for invalid in (b"\x04\xfb\x01\x01\x55", b"\x04\xfb\x20", b"\x04\xfb\x01"):
        driver.uart.write(invalid)
        sleep_ms(600)
        assert driver.uart.read() is None
        assert driver.check_play_status() == 0
    driver.uart.write(b"\x04\xfb\x03\x06\x00\x00\x08")
    sleep_ms(30)
    assert driver.uart.read() == b"\xaa\x55\x02\xff\x04\x04"
    assert driver.check_play_status() == 0
    print("N9301_PROBE_REJECTED")
    assert driver.play_audio_by_index(3) == 3
    assert driver.check_play_status() == 1
    assert driver.pause_audio() == 2
    driver.play_audio()
    assert driver.uart.read() == b"\x04\xfb\x02\x00\x01\x02"
    assert driver.check_play_status() == 1
    assert driver.stop_audio() == 0
    assert driver.select_audio_num(5) == 5
    assert driver.check_play_status() == 0
    assert driver.next_audio() == 6
    assert driver.previous_audio() == 5
    assert driver.get_current_audio_number() == 5
    driver.set_volume(15)
    assert driver.get_volume() == 15
    driver.set_play_mode(1)
    assert driver.get_play_mode() == 1
    assert driver.check_play_status() == 0
    print("N9301_PROBE_CONTROLS", driver.check_play_status(),
          driver.get_current_audio_number(), driver.get_volume(), driver.get_play_mode())
print("N9301_PROBE_PASS")
