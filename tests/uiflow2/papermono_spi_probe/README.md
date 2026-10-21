# PaperMono SPI transport probe

This probe checks the low-level SPI transport used by PaperMono peripherals:

- SX1262 responses are delivered through the GDMA RX path;
- CS stays asserted across opcode and argument bytes;
- 2-, 3- and 4-byte SPI transactions complete in sequence;
- subsequent transactions start from the current GDMA link head.

The on-screen result must be `status=ok`. The unresolved IDF bus-lock stall
for a single transaction larger than four bytes is documented in the LoRa
probe; this probe intentionally stays on the verified <=4-byte path.
