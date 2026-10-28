# UIFlow2 官方源码候选修正

此目录保存针对固定官方源码的候选补丁，不替换平台默认参考固件。
原厂冻结固件、与源码构建匹配的 SDK 原版、候选源码覆盖和候选固件是不同
验证 lane。原厂失败必须保留；官方源码 commit 相同，也不能据此认定构建
产物与发布固件相同。下表说明修复行为、实际验证入口与边界，不是全接口
通过表。所有设备执行均为 virtual-device validation；物理硬件未验证。

| 补丁 | 修正范围 | 验证边界 |
| --- | --- | --- |
| [0001-m5ui-native-marshalling.patch](0001-m5ui-native-marshalling.patch) | Canvas 三角点数组整体回写；Image 单参数浮点 scale 转整数；Spinbox 整数 step 按小数位缩放 | CoreS3 独立 `candidate_m5ui` 包与原版对照，保留相对导入和原 `M5Base`；原生状态及指定像素验证，stock 失败保留 |
| [0002-requests2-form-encoding.patch](0002-requests2-form-encoding.patch) | form 键值按 UTF-8 字节转义，空格编码为 `+`；字符串请求体按编码后的字节数设置长度 | CoreS3 / Cardputer-ADV 真实受控 HTTP peer，原版与候选源码对照；只覆盖列出的 form / UTF-8 请求体案例，见[复现](README-requests2.md) |
| [0003-display-raw-buffer-length.patch](0003-display-raw-buffer-length.patch) | `drawRawBuf` 的公开字节长度转换为 RGB565 像素数；在 `startWrite` 前拒绝非法长度 | CoreS3 matching SDK 原版 / 候选固件，同程序精确像素及长度负控；历史 `len(raw)//2` 规避调用不代表原厂已修复 |
| [0004-display-path-length-unbox.patch](0004-display-path-length-unbox.patch) | 将 `mp_obj_len` 的 tagged small-int 解包，再执行原有 128 字符路径限制 | CoreS3 matching SDK 原版 / 候选固件的 PNG、BMP、JPEG、自动识别路径和 bytes 域；只修复原被误判的 64–127 字符路径 |
| [0005-lvgl-roller-final-option.patch](0005-lvgl-roller-final-option.patch) | `set_selected_str` 精确匹配完整选项，包括末行；前缀和不存在的值不误选 | CoreS3 stock、matching SDK 原版与原生 LVGL 候选固件分别记录；以实际 selected index / string 为 oracle |
| [0006-lvgl-python-event-identity.patch](0006-lvgl-python-event-identity.patch) | 按 Python 回调及原 user-data 身份移除事件；事件和 descriptor getter 保留原调用者对象身份 | CoreS3 object / display / indev 的原生回调、descriptor 和字典身份对照；未匹配注册仍须保留，不能外推其它回调类型 |
| [0007-labelplus-optional-timer.patch](0007-labelplus-optional-timer.patch) | 关闭自动更新或周期为零时仍可手动更新、选 key 和 deinit；只操作已创建的 `SoftTimer` | 独立 `candidate_label_plus.py` 源码覆盖，以实际 HTTP 值和定时器新增请求为 oracle；stock 冻结库失败独立保留 |
| [0008-lvgl-native-subclass-wrapper.patch](0008-lvgl-native-subclass-wrapper.patch) | 将未直接登记的原生子类包装为最近已登记的基类，保留真实 class 身份 | CoreS3 matching SDK 原版 / 候选固件，以真实内部 label / button 子对象及其方法验证；不是任意自定义类兼容性声明 |
| [0009-lvgl-writable-callback-string.patch](0009-lvgl-writable-callback-string.patch) | 可写 `char *` 回调参数保留原 buffer 地址；`const char *` 仍转换为字符串 | CoreS3 文件系统原生回调写回及目录条目内容对照；只覆盖实际可写回调路径，不授予其它文件系统后端通过 |
| [0010-mbedtls-epoch.patch](0010-mbedtls-epoch.patch) | 1970 epoch 端口直接返回 Unix 秒数，避免重复加上 1970–2000 偏移；保留 2000 epoch 分支 | StopWatch / StickS3 / Core2 matching source preimage 均为证书过期 ERROR，候选固件三台均 `5/5` `CERT_REQUIRED` mTLS HTTPS PASS；1996 RTC 诊断不计 stock，通过范围见[TLS 说明](README-tls.md) |
| [0011-usb-buffer-readinto.patch](0011-usb-buffer-readinto.patch) | 修正未定义的 `to_r4`，返回实际复制并消费的字节数，覆盖空读、零长度和部分读取 | 双板 guest 内精确官方 Python 模块原版 / 候选对照；只证明 Buffer 字节与 IRQ 临界区契约，不证明 OTG 枚举或 endpoint 传输 |
| [0012-lvgl-menu-page-helpers.patch](0012-lvgl-menu-page-helpers.patch) | 对首参数为其它资源的 widget namespace helper 生成独立 static alias；保留 canonical struct / calendar 实例绑定 | CoreS3 matching SDK 原版 / 候选的真实 menu page、calendar parent、scale section 等 typed 资源；每个别名须实际调用，不从 owner 或候选继承 stock 通过 |
| [0013-lvgl-unsigned-word-arguments.patch](0013-lvgl-unsigned-word-arguments.patch) | `uint32` 和 unsigned native-word 参数保留完整位模式，避免高位值经过 signed-range 转换 | CoreS3 matching SDK 原版 / 候选的高位动画 speed 和 ARGB 等已执行域；signed / 64-bit 转换保持原实现 |
| [0014-widgets-qrcode-text.patch](0014-widgets-qrcode-text.patch) | `Widgets.QRCode.setText` 保存新字符串，擦除旧 QR 区域并重新编码绘制 | StopWatch / StickS3 / Core2 matching source preimage 三台均解码旧文本失败，候选固件三台均解码 `UPDATED-API` PASS；CoreS3 / Cardputer-ADV 既往证据保留，不以非空图代替文本验证 |
| [0015-lvgl-object-user-data.patch](0015-lvgl-object-user-data.patch) | 应用 user-data 独立持有，不覆盖用于 Python wrapper 身份及删除失效的原生槽位 | CoreS3 matching SDK 原版 / 候选，以 object、event、group、screen getter 的精确对象身份和删除生命周期验证；stock 结果不覆盖 |
| [0016-lvgl-custom-animation-lookup.patch](0016-lvgl-custom-animation-lookup.patch) | custom animation 按 `custom_exec_cb` 查找 / 删除，保留变量过滤、NULL 通配和删除回调修改链表的安全遍历 | 精确源码 C 正反回归及 CoreS3 matching SDK 原版 / 候选原生回调验证；不外推未执行动画参数域 |
| [0017-lvgl-observer-object-cleanup.patch](0017-lvgl-observer-object-cleanup.patch) | 显式移除 observer 时先解绑其精确 object-delete 订阅；subject 清理不误删同对象上其它 subject 的订阅 | 精确源码回调链表 C 回归及 CoreS3 stock / matching SDK 原版 / 候选三 lane；检查订阅成员身份、保留的通知和自动删除，清理 repair 不把原失败转为通过 |
| [0018-lvgl-cache-entry-allocation.patch](0018-lvgl-cache-entry-allocation.patch) | 在 payload 后方初始化并返回真正的 metadata header，保持零填充 payload 和原分配基址释放契约 | 完整固定源码 C 正反回归及 CoreS3 matching SDK 原版 / 候选同源程序；先检查原始 metadata，再测完整 payload、指针、引用及 delete，失败后手动初始化仅用于清理 |
| [0019-widgets-qrcode-geometry.patch](0019-widgets-qrcode-geometry.patch) | `QRCode.setCursor` / `setSize` 修改位置或宽度前，按原几何擦除旧区域，避免移动和缩小时留下旧图块 | 精确原生方法 C++ 正反回归及 CoreS3 stock / matching SDK 原版 / 候选同源程序；新 QR 解码与旧独占区域清空分别检查，版本切换保持原几何；不外推其它板卡 |
| [0020-display-canvas-allocation.patch](0020-display-canvas-allocation.patch) | 拒绝非正宽高；底层 createSprite 分配失败时释放 Canvas 并抛 MemoryError，避免发布空对象后 show 写入 NULL | 精确原生函数 C++ 16 个正反域、CoreS3 stock / matching SDK HCI-cache / 独立候选同源六项检查，候选 19/19 收据检查；不增加 DMA 内存或声称任意尺寸可分配 |
| [0021-ble-advertising-uuid32.patch](0021-ble-advertising-uuid32.patch) | 两个 BLE advertising 解码器不再把 4-byte UUID 当作 8-byte `double`；将原始 4-byte 蓝牙 UUID 交给 `bluetooth.UUID` | StopWatch / StickS3 / Core2 stock 32-bit 失败保留；同 VM 候选源码包在 16/32-bit 向量上通过，见 2026-10-28 三设备证据 |
| [0022-modbus-transform-frame.patch](0022-modbus-transform-frame.patch) | `ModbusRTUFrame.transform_frame` 用源 TCP frame 的字段直接构造 RTU frame，不再先创建非法 `func_code=0` 对象 | StopWatch / StickS3 / Core2 stock 失败保留；同 VM 候选源码包验证 function-03 request、response 和 exception frame 的精确 RTU bytes/CRC |
| [0023-modbus-async-socket.patch](0023-modbus-async-socket.patch) | MicroPython 下不再调用不存在的 `asyncio.Loop.sock_recv`，改为有界、可让出执行权的 `select.poll` + socket receive；CPython 路径保留 | StopWatch / StickS3 / Core2 stock 八个 async TCP 方法均报 `sock_recv`；候选须由真实 owned Modbus peer 验证读、写和回读 |
| [0024-display-draw-pixel-transaction.patch](0024-display-draw-pixel-transaction.patch) | Python `Display.drawPixel` 使用嵌套安全的 `startWrite/endWrite`，让 framebuffer-backed panel 的 auto-display 提交 dirty range | StopWatch preimage 的 standalone 奇/偶像素不出现；StopWatch / StickS3 / Core2 候选通过 standalone、相邻像素保留和用户显式外层事务；真机 NOT RUN |

相邻 JSON 固定官方源码及 preimage / candidate SHA；`0001` 使用多文件
`files` 清单，`0002` 使用 `source_path` / `postimage_sha256`。含
`patch_sha256` 的元数据也须核对补丁本身。每项应在独立源码副本上执行
`git apply --check`、应用、postimage hash 核对和反向应用检查，不能修改原 SDK
来制造匹配的 preimage。

同文件叠加时，必须使用 `stack_preimage_sha256` /
`stack_candidate_sha256`，而不是独立补丁的 candidate hash：

- GFX：`0003 → 0004`。
- Widgets QR：`0014 → 0019`。
- LVGL generator：`0006 → 0008 → 0009 → 0012 → 0013 → 0015`。

其它补丁修改不同文件，但仍需独立及整栈重放。生成绑定后的增量固件必须
保存实际 patch 清单、binding / source / firmware hash 与构建 receipt；增量
relink 不等于独立冷构建。源码 hash 或离线 C 通过也不等于设备功能通过。

复现入口见 [UI 验证说明](../../tests/uiflow2/api_sweep/README-ui.md)、
[硬件及 USB 说明](../../tests/uiflow2/api_sweep/README-hardware.md)和上述专项文档。
大型固件、源树、编译产物、完整串口、帧及 ZIP 留在 ignored 存储；公开结果只
保留经审查的精简凭据。所有 guest 运行通过可见 Device Service 会话，先取
evidence ZIP，再以 `purge=0` 停止并检查历史与进程清理。
