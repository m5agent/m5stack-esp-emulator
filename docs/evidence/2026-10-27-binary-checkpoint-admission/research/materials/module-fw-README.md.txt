## M5Module-4Relay-Internal-FW

### Register

- Device addr: 0x26
- 10H (R/W) Relay Control

| Bit      | Default | Description    |
| -------- | ------- | -------------- |
| bit[4:7] | 0000    | reserved bits  |
| bit[3]   | 0       | Relay 4 status |
| bit[2]   | 0       | Relay 3 status |
| bit[1]   | 0       | Relay 2 status |
| bit[0]   | 0       | Relay 1 status |

Note: 0 is OFF, 1 is ON
