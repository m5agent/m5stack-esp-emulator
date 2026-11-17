# Tab5 原生 ST7123 单点触控

2026-11-17 · virtual-device validation。使用一个隔离的 Device Service
worker 按实际 Flash SHA 启动两个原版。会话均走无匹配 ELF 的普通入口。

- 原版 Arduventure 1.0.0 通过 GPIO31/32 软件 I²C 保留 ST7123 识别和
  720×1280 原始帧。普通输入进入 HP I²C1 的 `0x55` 从设备。空白点击
  保持画面，速度按钮从 1× 切到 2×，B 打开真实新游戏名字页。该页的
  右、下、左、上依次将光标从 A 移到 B、K、J、A，B 写入字符，A 删去
  后恢复原始名字页。十次点击每次均读取完整触点和释放。
- 独立 ESP-IDF 5.5.4 [来宾探针](../../../tests/firmware/tab5_st7123/README.md)
  已验证 GPIO23 高电平空闲对照，以及三次低有效 IRQ、对应 I²C 坐标
  与释放。三个精确触点为 (0,1279)、(719,0)、(310,608)。
- 同一 worker 的原版 CarPlay 仍使用 GT911/ILI9881C，空白拖动有
  24/24 确认且画面不变，后续单击打开原版配对清除确认框。

常规固件审核对同一原版通过启动与 60 秒观察。默认中心点击被读取但没有
游戏动作，通用拖动及物理按键计划未覆盖屏幕 A/B，审核仍为 SIM_PARTIAL。
上述语义点击取证来自同一固件的专门 Device Service 复验。

所有记录均保留证据 ZIP 后停止，会话 Flash 和租约清理完成。ST7123
覆盖单触点点击。ST7123 拖动、多点、浏览器和物理触控未验证；Arduventure
验证到新游戏名字页的输入反应。CarPlay 未验证 USB/iPhone。没有提交 Burner。

[执行与产物 SHA](summary.json) · [Device Service 配置](../../device-service-api.md#create-a-reference-uiflow2-device)
