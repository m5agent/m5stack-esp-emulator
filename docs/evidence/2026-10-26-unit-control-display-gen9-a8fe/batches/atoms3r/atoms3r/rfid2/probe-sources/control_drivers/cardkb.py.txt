# SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
#
# SPDX-License-Identifier: MIT

from micropython import schedule
from machine import I2C
from machine import UART

try:
    import m5espnow
except ImportError:
    pass
import sys

if sys.platform != "esp32":
    from typing import Literal


class KeyCode:
    """Key code constants for CardKB unit.

    This class defines the key codes for special keys on the CardKB keyboard.

    MicroPython Code Block:

        .. code-block:: python

            from cardkb import KeyCode

            if key == KeyCode.KEYCODE_ENTER:
                print("Enter key pressed")
    """

    KEYCODE_UNKNOWN = 0x00
    KEYCODE_BACKSPACE = 0x08
    KEYCODE_TAB = 0x09
    KEYCODE_ENTER = 0x0A
    KEYCODE_ESC = 0x1B
    KEYCODE_SPACE = 0x20
    KEYCODE_DEL = 0x7F

    KEYCODE_LEFT = 180
    KEYCODE_UP = 181
    KEYCODE_DOWN = 182
    KEYCODE_RIGHT = 183


_V2_MOD_SHIFT = 0x22

_V2_KEYCODE_TO_CHAR = {
    0x1E: "1",
    0x1F: "2",
    0x20: "3",
    0x21: "4",
    0x22: "5",
    0x23: "6",
    0x24: "7",
    0x25: "8",
    0x26: "9",
    0x27: "0",
    0x28: "\n",
    0x29: "\x1b",
    0x2A: "\b",
    0x2B: "\t",
    0x2C: " ",
    0x2D: "-",
    0x2E: "=",
    0x2F: "[",
    0x30: "]",
    0x31: "\\",
    0x33: ";",
    0x34: "'",
    0x35: "`",
    0x36: ",",
    0x37: ".",
    0x38: "/",
    0x4F: KeyCode.KEYCODE_RIGHT,
    0x50: KeyCode.KEYCODE_LEFT,
    0x51: KeyCode.KEYCODE_DOWN,
    0x52: KeyCode.KEYCODE_UP,
}

_V2_SHIFT_KEYCODE_TO_CHAR = {
    0x1E: "!",
    0x1F: "@",
    0x20: "#",
    0x21: "$",
    0x22: "%",
    0x23: "^",
    0x24: "&",
    0x25: "*",
    0x26: "(",
    0x27: ")",
    0x2D: "_",
    0x2E: "+",
    0x2F: "{",
    0x30: "}",
    0x31: "|",
    0x33: ":",
    0x34: '"',
    0x35: "~",
    0x36: "<",
    0x37: ">",
    0x38: "?",
}


def _v2_keycode_to_code(keycode, modifier=0):
    if 0x04 <= keycode <= 0x1D:
        base = ord("A" if modifier & _V2_MOD_SHIFT else "a")
        return base + keycode - 0x04

    if modifier & _V2_MOD_SHIFT:
        value = _V2_SHIFT_KEYCODE_TO_CHAR.get(keycode)
        if value is not None:
            return ord(value)

    value = _V2_KEYCODE_TO_CHAR.get(keycode)
    if isinstance(value, str):
        return ord(value)
    return value


class CardKBUnit:
    """Create a CardKBUnit object.

    :param args: Positional arguments passed to the underlying communication class.
    :param int mode: The communication mode. Default modes are:

        - ``CardKBUnit.CardKB_I2C_MODE`` : I2C mode
        - ``CardKBUnit.CardKB_UART_MODE`` : UART mode
        - ``CardKBUnit.CardKB_ESP_NOW_MODE`` : ESP-NOW mode

    .. note::

        This is a factory class. It returns an instance of the appropriate subclass
        based on the specified mode.

    UiFlow2 Code Block:

        |init.png|

    MicroPython Code Block:

        .. code-block:: python

            from cardkb import CardKBUnit
            from hardware import I2C, Pin

            # I2C mode
            i2c0 = I2C(0, scl=Pin(33), sda=Pin(32), freq=100000)
            cardkb_0 = CardKBUnit(i2c0, mode=CardKBUnit.CardKB_I2C_MODE)

            # UART mode
            cardkb_0 = CardKBUnit(2, port=(33, 32), mode=CardKBUnit.CardKB_UART_MODE)

            # ESP-NOW mode
            cardkb_0 = CardKBUnit(mode=CardKBUnit.CardKB_ESP_NOW_MODE)
    """

    CardKB_I2C_MODE = 0
    CardKB_UART_MODE = 1
    CardKB_ESP_NOW_MODE = 2

    KEY_STATE_PRESS = 0x01
    KEY_STATE_RELEASE = 0x02

    def __new__(cls, *args, **kwargs):
        """Create a new CardKBUnit instance based on the specified communication mode.

        :param args: Positional arguments to be passed to the subclass constructors.
        :param kwargs: Keyword arguments, must include ``mode`` to specify the communication mode.
        :raises ValueError: If an invalid mode is specified.
        :return: An instance of ``CardKBI2C``, ``CardKBUART``, or ``CardKBESPNOW``.

        MicroPython Code Block:

            .. code-block:: python

                cardkb_0 = CardKBUnit(i2c0, mode=CardKBUnit.CardKB_I2C_MODE)
        """
        mode = kwargs.get("mode", cls.CardKB_I2C_MODE)
        if mode == cls.CardKB_I2C_MODE:
            cls.instance = CardKBI2C(args[0], **kwargs)
        elif mode == cls.CardKB_UART_MODE:
            cls.instance = CardKBUART(args[0], **kwargs)
        elif mode == cls.CardKB_ESP_NOW_MODE:
            cls.instance = CardKBESPNOW(**kwargs)
        else:
            raise ValueError("Invalid mode specified")
        return cls.instance


class CardKBBase:
    """Base class for CardKB unit communication.

    This class provides the common interface and logic for all CardKB communication modes.
    """

    FRAME_HEADER = 0xAA
    FRAME_DATA_LEN = 0x03
    V2_REPORT_LEN = 0x08
    V2_FRAME_SIZE = V2_REPORT_LEN + 3
    V2_KEY_SLOT_COUNT = 6
    V2_ERROR_ROLLOVER = 0x01

    def __init__(self) -> None:
        self._keys = []
        self._handler = None
        self._last_report = [0] * self.V2_REPORT_LEN

    def _is_valid_ack(self, buf):
        if not buf or len(buf) != 4:
            return None
        data_len, key_id, key_state, checksum = buf
        calc = (data_len + key_id + key_state) & 0xFF
        if data_len != self.FRAME_DATA_LEN or checksum != calc:
            return None
        return (key_id, key_state)

    def _is_valid_v2_frame(self, frame):
        if not frame or len(frame) != self.V2_FRAME_SIZE:
            return None
        if frame[0] != self.FRAME_HEADER or frame[1] != self.V2_REPORT_LEN:
            return None
        checksum = 0
        for value in frame[1:-1]:
            checksum = (checksum + value) & 0xFF
        if checksum != frame[-1]:
            return None
        return frame[2:-1]

    def _report_keycodes(self, report):
        if not report or len(report) != self.V2_REPORT_LEN:
            return []
        keycodes = []
        for keycode in report[2:]:
            if keycode:
                keycodes.append(keycode)
        if len(keycodes) == self.V2_KEY_SLOT_COUNT and keycodes[0] == self.V2_ERROR_ROLLOVER:
            return []
        return keycodes

    def _queue_v2_report(self, report, as_char=False):
        old_report = self._last_report
        old_keys = self._report_keycodes(old_report)
        new_keys = self._report_keycodes(report)
        modifier = report[0] if report else 0
        before = len(self._keys)

        if as_char:
            emit_keys = (
                new_keys
                if list(report) == list(old_report)
                else [keycode for keycode in new_keys if keycode not in old_keys]
            )
            for keycode in emit_keys:
                code = _v2_keycode_to_code(keycode, modifier)
                if code is not None:
                    self._keys.append(code)
        elif list(report) == list(old_report):
            for keycode in new_keys:
                self._keys.append((keycode, CardKBUnit.KEY_STATE_PRESS))
        else:
            for keycode in old_keys:
                if keycode not in new_keys:
                    self._keys.append((keycode, CardKBUnit.KEY_STATE_RELEASE))
            for keycode in new_keys:
                if keycode not in old_keys:
                    self._keys.append((keycode, CardKBUnit.KEY_STATE_PRESS))

        self._last_report = list(report)
        return len(self._keys) != before

    def _handle_frame(self, frame):
        if not frame or frame[0] != self.FRAME_HEADER:
            return False

        if len(frame) == 5 and frame[1] == self.FRAME_DATA_LEN:
            buf = self._is_valid_ack(frame[1:])
            if buf is not None:
                self._keys.append(buf)
                return True
            return False

        if len(frame) == self.V2_FRAME_SIZE and frame[1] == self.V2_REPORT_LEN:
            report = self._is_valid_v2_frame(frame)
            if report is not None:
                return self._queue_v2_report(report)
        return False

    def get_report(self):
        """Get the latest V2 keyboard report.

        :return: The report ``(modifier, reserved, key1, ..., key6)``.
        :rtype: tuple
        """
        return tuple(self._last_report)

    def _get_key(self):
        raise NotImplementedError("Subclasses should implement this method!")

    def get_key(self):
        """Get the next key from the key buffer.

        :return: The key value (int or tuple depending on mode)

        UiFlow2 Code Block:

            |get_key.png|

        MicroPython Code Block:

            .. code-block:: python

                key = cardkb_0.get_key()
                print(key)
        """
        if self._keys:
            return self._keys.pop(0)
        else:
            if self._get_key():
                return self._keys.pop(0) if self._keys else None
            else:
                return None

    def get_string(self):
        """Get the next key as a string.

        :return: The string representation of the next key.
        :rtype: str

        UiFlow2 Code Block:

            |get_string.png|

        MicroPython Code Block:

            .. code-block:: python

                s = cardkb_0.get_string()
                print(s)
        """
        return str(self.get_key())

    def get_char(self):
        """Get the next key as a character.

        :return: The character corresponding to the next key code.
        :rtype: str

        UiFlow2 Code Block:

            |get_char.png|

        MicroPython Code Block:

            .. code-block:: python

                c = cardkb_0.get_char()
                print(c)
        """
        return chr(self.get_key())

    def is_pressed(self) -> bool:
        """Check whether any key is currently pressed.

        :return: ``True`` if a key is pressed, ``False`` otherwise.
        :rtype: bool

        UiFlow2 Code Block:

            |is_pressed.png|

        MicroPython Code Block:

            .. code-block:: python

                if cardkb_0.is_pressed():
                    print("Key pressed!")
        """
        if self._keys:
            return True
        return self._get_key()

    def set_callback(self, handler):
        """Set the callback function for key press events.

        :param handler: The callback function to invoke when a key is pressed.
            The callback receives the CardKB instance as its argument.

        UiFlow2 Code Block:

            |i2c_callback.png|

            |callback.png|


        MicroPython Code Block:

            .. code-block:: python

                # I2C mode example
                def on_key_pressed(kb):
                    print("Key pressed:", kb.get_char())

                cardkb_0.set_callback(on_key_pressed)

                # UART/ESP-NOW mode example
                def on_key_event(kb):
                    key_id, key_state = kb.get_key()
                    print("Key event - ID:", key_id, "State:", key_state)
        """
        self._handler = handler

    def tick(self) -> None:
        """Poll for key events and trigger the callback if a key is pressed.

        This method should be called periodically in the main loop to process key events.

        UiFlow2 Code Block:

            |tick.png|

        MicroPython Code Block:

            .. code-block:: python

                while True:
                    cardkb_0.tick()
        """
        if self.is_pressed() and self._handler:
            schedule(self._handler, self)


class CardKBI2C(CardKBBase):
    """CardKB unit driver over I2C communication.

    :param I2C i2c: The I2C bus instance.
    :param int address: The I2C address of the CardKB unit. Defaults to ``0x5F``.
    :param mode: Ignored. Reserved for factory compatibility.

    :raises Exception: If the CardKB unit is not found on the I2C bus.

    .. note::

        Do not instantiate this class directly. Use :class:`CardKBUnit` with
        ``mode=CardKBUnit.CardKB_I2C_MODE`` instead.

    MicroPython Code Block:

        .. code-block:: python

            from hardware import I2C, Pin
            from cardkb import CardKBUnit

            i2c0 = I2C(0, scl=Pin(33), sda=Pin(32), freq=100000)
            cardkb_0 = CardKBUnit(i2c0, mode=CardKBUnit.CardKB_I2C_MODE)
    """

    CardKB_I2C_ADDR = 0x5F
    CardKB_FW_REG = 0xF1
    CardKB_STATUS_REG = 0x00
    CardKB_SEQUENCE_REG = 0x01
    CardKB_REPORT_LEN_REG = 0x02
    CardKB_REPORT_REG = 0x03

    def __init__(self, i2c: I2C, address: int = CardKB_I2C_ADDR, mode=None) -> None:
        self._i2c = i2c
        self._i2c_addr = address
        self._v2_report_mode = False
        self._last_sequence = None
        if self._i2c_addr not in self._i2c.scan():
            raise Exception("CardKB unit not found in Grove")
        super().__init__()

        try:
            report_len = self._i2c.readfrom_mem(
                self._i2c_addr, CardKBI2C.CardKB_REPORT_LEN_REG, 1
            )[0]
            if report_len == self.V2_REPORT_LEN:
                self._v2_report_mode = True
                self._last_sequence = self._i2c.readfrom_mem(
                    self._i2c_addr, CardKBI2C.CardKB_SEQUENCE_REG, 1
                )[0]
        except OSError:
            pass

        if self._v2_report_mode:
            return

        try:
            while True:
                buf = self._i2c.readfrom(self._i2c_addr, 1)
                if buf[0] == KeyCode.KEYCODE_UNKNOWN:
                    break
        except OSError:
            pass

    def _get_key(self):
        if self._v2_report_mode:
            try:
                sequence = self._i2c.readfrom_mem(
                    self._i2c_addr, CardKBI2C.CardKB_SEQUENCE_REG, 1
                )[0]
                if sequence == self._last_sequence:
                    return False
                report = self._i2c.readfrom_mem(
                    self._i2c_addr, CardKBI2C.CardKB_REPORT_REG, self.V2_REPORT_LEN
                )
                self._last_sequence = sequence
                return self._queue_v2_report(report, as_char=True)
            except OSError:
                return False

        buf = self._i2c.readfrom(self._i2c_addr, 1)
        if buf[0] != 0:
            self._keys.append(buf[0])
            return True
        return False

    def get_firmware_version(self):
        """Read the firmware version from the CardKB unit.

        :return: The firmware version byte.
        :rtype: int

        MicroPython Code Block:

            .. code-block:: python

                version = cardkb_0.get_firmware_version()
                print("Firmware version:", version)
        """
        return self._i2c.readfrom_mem(self._i2c_addr, CardKBI2C.CardKB_FW_REG, 1)[0]


class CardKBUART(CardKBBase):
    """CardKB unit driver over UART communication.

    :param int id: The UART bus ID (0, 1, or 2). Defaults to ``1``.
    :param port: A list or tuple of ``(rx_pin, tx_pin)``.
    :param mode: Ignored. Reserved for factory compatibility.

    .. note::

        Do not instantiate this class directly. Use :class:`CardKBUnit` with
        ``mode=CardKBUnit.CardKB_UART_MODE`` instead.

    MicroPython Code Block:

        .. code-block:: python

            from cardkb import CardKBUnit

            cardkb_0 = CardKBUnit(2, port=(33, 32), mode=CardKBUnit.CardKB_UART_MODE)
    """

    def __init__(self, id: Literal[0, 1, 2] = 1, port: list | tuple = None, mode=None) -> None:
        self._uart_bus = UART(id, tx=port[1], rx=port[0])
        self._uart_bus.init(115200, bits=8, parity=None, stop=1)
        self._rx_buf = bytearray()
        super().__init__()

    def _get_key(self):
        size = self._uart_bus.any()
        if size <= 0:
            return False

        data = self._uart_bus.read(size)
        if not data:
            return False

        self._rx_buf.extend(data)
        before = len(self._keys)

        while len(self._rx_buf) >= 2:
            if self._rx_buf[0] != self.FRAME_HEADER:
                self._rx_buf = self._rx_buf[1:]
                continue

            data_len = self._rx_buf[1]
            if data_len == self.FRAME_DATA_LEN:
                frame_size = 5
            elif data_len == self.V2_REPORT_LEN:
                frame_size = self.V2_FRAME_SIZE
            else:
                self._rx_buf = self._rx_buf[1:]
                continue

            if len(self._rx_buf) < frame_size:
                break

            frame = self._rx_buf[:frame_size]
            self._rx_buf = self._rx_buf[frame_size:]
            self._handle_frame(frame)

        return len(self._keys) != before

    def tick(self):
        """Poll the key buffer and trigger the callback if a key is available.

        This method should be called periodically in the main loop to process
        key events received via UART.

        MicroPython Code Block:

            .. code-block:: python

                while True:
                    cardkb_0.tick()
        """
        if self.is_pressed() and self._handler:
            schedule(self._handler, self.get_key())


class CardKBESPNOW(CardKBBase):
    """CardKB unit driver over ESP-NOW wireless communication.

    :param mode: Ignored. Reserved for factory compatibility.

    .. note::

        Do not instantiate this class directly. Use :class:`CardKBUnit` with
        ``mode=CardKBUnit.CardKB_ESP_NOW_MODE`` instead.

    .. note::

        This class uses a broadcast MAC address (``ffffffffffff``) and fixes the
        Wi-Fi channel to 0. Key data is received asynchronously via IRQ callback.

    MicroPython Code Block:

        .. code-block:: python

            from cardkb import CardKBUnit

            cardkb_0 = CardKBUnit(mode=CardKBUnit.CardKB_ESP_NOW_MODE)
    """

    def __init__(self, mode=None) -> None:
        self._esp_now = m5espnow.M5ESPNow(0)  # channel fix to 0
        self._esp_now.set_add_peer("ffffffffffff")
        self._esp_now.set_irq_callback(self.espnow_recv_callback)
        super().__init__()

    def espnow_recv_callback(self, espnow_obj):
        """Callback function invoked when an ESP-NOW packet is received.

        :param espnow_obj: The ESP-NOW object containing the received data.
        :return: ``True`` if the frame is valid and a key was appended, ``False`` otherwise.
        :rtype: bool
        """
        _, event_data = espnow_obj.recv_data()
        frame = event_data
        return self._handle_frame(frame)

    def get_key(self):
        """Get the next key from the buffer received via ESP-NOW.

        :return: The key tuple ``(key_id, key_state)``, or ``None`` if the buffer is empty.
        :rtype: tuple or None

        MicroPython Code Block:

            .. code-block:: python

                key = cardkb_0.get_key()
                if key:
                    print("key_id:", key[0], "key_state:", key[1])
        """
        if self._keys:
            return self._keys.pop(0)
        else:
            return None

    def is_pressed(self) -> bool:
        """Check whether any key data is buffered from ESP-NOW.

        :return: ``True`` if there is buffered key data, ``False`` otherwise.
        :rtype: bool

        MicroPython Code Block:

            .. code-block:: python

                if cardkb_0.is_pressed():
                    print("Key received via ESP-NOW!")
        """
        if self._keys:
            return True
        return False

    def tick(self):
        """Poll the key buffer and trigger the callback if a key is available.

        This method should be called periodically in the main loop to process
        key events received via ESP-NOW.

        MicroPython Code Block:

            .. code-block:: python

                while True:
                    cardkb_0.tick()
        """
        if self.is_pressed() and self._handler:
            schedule(self._handler, self.get_key())
