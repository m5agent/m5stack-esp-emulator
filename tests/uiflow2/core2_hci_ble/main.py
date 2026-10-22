import time

from bleuart import BLEUARTServer


print("CORE2_HCI_MAIN_START")
server = BLEUARTServer(name="M5-CORE2-HCI", verbose=True)


def on_receive():
    payload = bytes(server.read())
    print("CORE2_HCI_BLE_RX", payload)
    server.write(b"ACK:" + payload)
    print("CORE2_HCI_BLE_ACK_SENT")


server.irq(on_receive)
print("CORE2_HCI_BLE_READY")

while True:
    print("CORE2_HCI_ALIVE")
    time.sleep(1)
