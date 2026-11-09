---
name: m5stack-browser-simulator
description: Run a compatible merged M5Stack firmware BIN on the public GitHub Pages emulator and inspect the actual guest screen. Use for online virtual flashing, boot and display smoke checks, or screenshots (线上模拟器、烧录 BIN 看画面). Use the Device Service skill for firmware composition or deeper diagnostics and the AIFlow skill for its code preview workflow.
---

# M5Stack Browser Simulator

Open the [online workbench](https://m5agent.github.io/m5stack-esp-emulator/) in desktop Chromium. Use its browser-local QEMU WASM runtime. A Device Service, local QEMU install and service credentials are unnecessary.

1. Confirm the exact device model and firmware. Filter by **浏览器可运行**, then choose the matching model marked **浏览器运行**. A model preview alone is insufficient. If the requested model is unavailable, report it and keep the result untested.
2. Under **加载固件**, choose **本地文件** and select the provided `.bin`. The workbench reads the file in the browser when running locally. Use a complete merged Flash image with the matching board, chip, bootloader, partition table and app. For separate flash segments, an app-only BIN or a ZIP, request the correct merged BIN. Use **链接** only for a public HTTPS BIN direct link that allows CORS. If browser control cannot select local files, give the user the picker steps. If there is no custom BIN and the user wants a demo, choose **UIFlow / 示例 → 屏幕与按键示例** and label it as the built-in demo.
3. Open **校验与运行选项**, choose **浏览器本地运行**, enter the known source SHA-256 if available and click **开始运行**. Allow for the initial Service Worker reload, WASM/ROM downloads and guest boot. Check the site error and **串口输出** if import fails or the screen stays blank. Report the stage reached and the actual error or last relevant serial lines.
4. Check the current guest screen. Use **平面触屏** for the unwrapped framebuffer if offered. Confirm the requested screen or visible change and capture a screenshot while the guest is running. A running status, 3D preview or a retained frame is insufficient. Use one supported touch or button input only when it helps reach or verify the requested screen.
5. Click **停止** and confirm the run ended. Use **下载本地运行记录** if structured evidence is needed. In the result, state the model, firmware name and SHA-256 if available, what the actual display showed, and the scope **virtual-device validation (browser WASM)**. If the expected screen was never observed, report it as unverified and give the observed state.
