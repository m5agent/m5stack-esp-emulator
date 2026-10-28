# UIFlow2 全接口验证入口

本目录将官方文档、候选官方源码与两个真实 guest 的导出对账，并保存逐接口
功能 recipe。CoreS3 使用 M5UI/LVGL；Cardputer-ADV 使用 Display/Widgets。
覆盖审计仍在推进；清单存在、recipe 已编写或 `EXECUTED` 均不表示功能通过。

## 清单

- `inventory_ui.source.json`：文档、原生 LVGL 继承/共享成员与 UI 功能 recipe。
- `inventory_hardware.source.json`：硬件、总线、配置及实例返回类型的公开接口。
- `inventory_system.source.json`：系统/通信候选接口及可选外接产品目录；源码
  commit 不自动绑定参考固件，须以两款固件实际导出重新准入。
- `inventory_api.source.json`：完整 Device Service OpenAPI operation 分母，
  正向场景和拒绝边界分开，入口见 [HTTP 验证说明](README-device-api.md)。

清单生成器接受独立官方 UIFlow2 源码目录。它们只读源码，不能建立 guest
执行证据；测试、示例及未公开 helper 不属于产品公开 API。官方明确文档化的
`M5ESPNow._bytes_to` 等方法即使带下划线也纳入契约。外接产品完整目录
只作为范围对账，联合功能验证使用选定 Unit；未选外设不计主机功能 PASS。

## 可见 guest 执行

使用项目 Python 环境和独立 Device Service；输出必须是新的 ignored 目录。
测试必须显式传入 `--api`，使用独立端口、状态目录和控制凭据；
8787 属于用户测试服务，Agent 不使用、停止或重启它。

```sh
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_guest.py \
  --api http://127.0.0.1:8788 \
  --device cores3 --source /path/to/finite_probe.py \
  --done-marker MY_PROBE_DONE --out-dir .work/api-sweep/my-probe \
  --token-file /path/to/device-service-token
```

`run_guest.py` 按实际固件分区表准备 VFS，通过 API 上传、创建可见会话、
分页读取串口、采集帧和 evidence ZIP，再 `purge=0` 停止并核验历史和 PID。
它不直接启动 QEMU。`run_hardware_guest.py` 在相同生命周期中按 guest
marker 驱动真实输入/QOM 请求。交互式程序使用 Device Service `/program`
和明确的 `expected_execution_id`；START、应用 READY 与测试完成分别记录。

## 结果规则

每个功能结论绑定设备、固件与运行时 SHA、源码、会话以及相关帧/输入/
controller 或 PCM/pcap 证据。setter/getter 对账、实际像素、输入事件和数据
传输按各接口契约验证。`PRESENT`、`CALL_OK`、导入成功和 HTTP 拒绝仅记录
其各自证据层；无法取得所需 fixture、模型或账户时保留具体 blocker。

原始固件、ZIP、Flash、完整串口和逐帧结果保留 ignored `.work/`，不提交。
源码库只保存必要的小型摘要、哈希和复现入口。全部会话结果属于
virtual-device validation，不能继承为真机结果或物理精度结论。

通信、TLS、BLE 固件 lane 与逐方法合并规则见
[protocol runners](README-protocols.md)。

SPI SD、独立 FAT/PCM/相机 oracle 与输入证据边界见
[hardware probes](README-hardware.md)。
