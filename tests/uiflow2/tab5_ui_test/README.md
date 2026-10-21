# Tab5 virtual UI test

This image replaces the VFS boot/main scripts in the emulator build of the
UIFlow2 Tab5 firmware. The build keeps the normal M5GFX drawing path, backs the
720x1280 raw panel memory with PSRAM, presents it as the physical landscape
1280x720 screen, and injects touch through a GDB-visible mailbox.

The one-click test writes the merged image to a 16 MiB virtual flash through
`esptool`, verifies every byte, then boots that same flash image for screenshot
and touch assertions.
