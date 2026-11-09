---
name: m5stack-browser-simulator
description: Load a compatible merged M5Stack firmware BIN on the public GitHub Pages emulator and verify guest boot and display (线上模拟器、烧录 BIN 看画面). Use the Device Service skill for firmware composition or deeper diagnostics and the AIFlow skill for its code preview workflow.
---

# M5Stack Browser Simulator

Open the [online workbench](https://m5agent.github.io/m5stack-esp-emulator/) in desktop Chromium. Select the exact model marked **浏览器运行** under **浏览器可运行**. If only its model preview is available, report browser execution as untested. Without browser control, give the manual steps and leave execution untested.

## Load and start

1. Under **加载固件 → 本地文件**, select a complete merged Flash `.bin` for the board, with its bootloader, partition table and app. Request a merged image for app-only BINs, separate segments or ZIPs. **链接** accepts a public HTTPS BIN direct link with CORS. If the user wants a demo, choose **UIFlow / 示例 → 屏幕与按键示例** and report the selected example.
2. With browser automation, use its file chooser or file input support (`#firmwareFile`). Verify the selected filename and, if readable, the file size before starting. If Chrome reports that the extension needs **Allow access to file URLs**, the automation tool was blocked before selection. Try Chrome's native file picker when available, or ask the user to select the file there and resume. Keep the BIN in the browser-local path. Classify a firmware rejection only after the workbench reads the file and reports a validation error.
3. In **校验与运行选项**, select **浏览器本地运行**, enter the known input SHA-256 if available, and click **开始运行**. Initial Service Worker reload and WASM/ROM downloads precede guest boot. A stock CoreS3 BIN on the `div8` profile can take longer than 30 seconds to reach its menu. Wait for the expected screen within a bounded timeout suited to the board and profile. Watch load progress, **串口输出**, and fresh frames during the wait.

## Verify and finish

- Distinguish guest boot, first fresh framebuffer and expected application UI. Advancing frame numbers, a black frame or a splash only establish frame delivery. Inspect **平面触屏** when available, confirm the requested UI or output, and capture it while the current guest is running. If it never appears, report the last stage, visible frame and relevant serial line or error. Stopping can retain a frame from that run.
- Test inputs only when requested or needed for the screen. For **CoreS3 LVGL + PIR** (**原始程序（正常时钟）**), map framebuffer coordinates `(160,184)` from 320×240 into the visible canvas, then send browser mouse down, hold about 650 ms, and release. Verify guest `touch_clicked` and a fresh **Clicks** change. For other firmware, use its own target and guest response. Record touch, PIR and button results separately. A delivered input and a guest response are separate observations.
- Treat the MicroPython editor as a separate check. Use the built-in UIFlow2 programming environment when the task requires executing code. A stock BIN can show its UI without a working browser REPL. Report the boot/display result independently of REPL availability or timeout.
- Click **停止** and confirm the run ended. For structured evidence use **下载本地运行记录**. If the automation download event times out, check the browser's recent downloads or the permitted download directory before retrying. Parse the `browser-local-qemu-evidence` JSON and match the session ID or start time, board and firmware. A download request alone does not prove a file was saved.
- Report the board, firmware, observed screen and scope **virtual-device validation (browser WASM)**. For custom BINs record `input_file_sha256` from the supplied bytes (or `receipt.firmwareInputSha256` when available) and `runtime_firmware_sha256` from `receipt.firmwareRuntimeSha256` or the older `receipt.firmwareSha256`. QEMU can fill the remaining Flash capacity with `0xFF`, so the hashes can differ for a valid image. Mark any unavailable digest as unverified.
