# 同固件 getter A/B 独立复核

日期：2026-10-26。结果：**PASS，无阻断缺证**。

本次只读复核已有原始资料；没有调用API、重查活进程或启动session/QEMU/guest。
“direct-PID验证”是运行时已保存的实测proof，本复核检查其源码方法、独立文件、report及running ZIP身份一致，不能把它称为本次新做了在线PID采样。

## 身份与原始证据

两份实际BIN逐字相同，SHA256均为：
`3ce76c8033131c6e0773406475c4b7342ae5f46d1e22240d690e6e61f9bba251`。
打包guest Python hash清单相同；送入controller的Unit runtime配置也逐字相同，
SHA为`1bdeb9ea345ea69e62cdd4fd761f701d5188a03a2beca2971088e28a1cb7e138`，
实际pins为yellow2/white1。

| 证据 | baseline-r1 | readback-mmio-r1 |
| --- | --- | --- |
| runtime SHA | `a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047` | `29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d` |
| direct-PID proof | VERIFIED，同running ZIP PID | VERIFIED，同running ZIP PID |
| 同worker generation | 9 | 10 |
| artifact hash检查 | 118/118 | 118/118 |
| ZIP | 10成员，全部hash/size/CRC匹配 | 10成员，全部hash/size/CRC匹配 |
| guest sample / raw | 60 / 480 | 60 / 480 |
| global / timer记录 | 60 / 240 | 60 / 240 |
| 严格稳定QOM | 76 | 75 |
| 排除QOM | 21 | 22 |
| phase-only过渡 | 4条，均排除 | 4条，均排除 |

四类记录均验证精确Cartesian网格完整且唯一，sample的phase/request向量也单独检查。
97份原始QOM逐一核实同session、running、live、available guest-QOM。
serial的before/after长度、prefix SHA与保存的phase metadata全部现场重算；
同sample1..8窗口、排除index集合及稳定记录与两份root分析JSON逐项相同。

每份ZIP serial均与外部serial.txt逐字相同；三路PNG独立解析为320×240且非空。
history同身份、stopped、flash_retained=false。最终off阶段帧相同是正常结果，
不能把最终帧当作四个非零阶段getter变化的视觉证明；数值结论来自完整serial/raw/QOM。

## getter与控制器结果

全部sample实测GPIO2 route73→LEDC ch0，global1=APB，timer0 resolution13，
分频寄存器计算为2000Hz；未使用的7个channel的DUTY/DUTY_R保持0。

| requested duty_u16 | baseline getter/raw count | new getter | new DUTY/DUTY_R raw | new整数count |
| --- | --- | --- | --- | --- |
| 0 | 0 / 0 | 0 | 0 | 0 |
| 16384 | 0 / 0 | 16384 | 32768 | 2048 |
| 32768 | 0 / 0 | 32768 | 65536 | 4096 |
| 49152 | 0 / 0 | 49152 | 98304 | 6144 |
| 65535 | 0 / 0 | 65535 | 131072 | 8192 |
| 0 | 0 / 0 | 0 | 0 | 0 |

new每个sample的两寄存器相等，整数count=`raw>>4`；getter等于
`min(65535, count<<(16-13))`。满档饱和65535的情况也按实际raw count核实。
baseline在QOM已有非零输出时两类读寄存器与getter仍为0。

root解析器现已补duplicate/complete-grid门禁；本复核独立重算该网格，
没有沿用其布尔结论。phase-only equality仍不足：在下一set后、下一PHASE前的
4条过渡样本保留于原始记录，全部从strict集合排除。

## 源码与允许结论

两个runner的唯一差异是冻结C源快照路径由旧source树改到新source树；采集/input
逻辑未变，见`runner-source-path-only.diff`。新C源快照SHA与冷构建manifest、
独立7patch replay的106文件清单一致，新runtime SHA也与该冷构建binary绑定。
父目录已冻结的receipt、SHA256SUMS、final-verification.json字节均未修改。

允许结论仅为：**同一custom诊断固件在新runtime中可以正确读取既有模型的稳定
set/update duty；旧runtime读取缺支导致的0现象得到同固件A/B证据支持。**

官方IDF current-cycle语义仍有独立边界：set_duty尚不生效，update后下一PWM周期
生效，get_duty返回present cycle。参考固定IDF的`ledc.h` lines279、299-301：
https://raw.githubusercontent.com/espressif/esp-idf/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_driver_ledc/include/driver/ledc.h
SHA256：`8ac4036faeca0c487f67af316baa944dc07e4ca689a683f9b2dba13843410378`。
本次没有测试pending/current分离、active latch、fade中间值、HPOINT/周期时序，
即时shadow读回不能关闭这些gap。没有原Buzzer.once、原发布固件完整功能、
private dirty SDK逐字来源、物理PWM/声学/电气PASS结论。

## 产物

- `review.py`：独立复核执行器；仅在本子目录写入。
- `review.json`：完整机器可读结果和逐phase表。
- `input-manifest.json`与`inputs/`：9份冻结report/analysis/proof/runner/analyzer输入。
- `run.log`、`SHA256SUMS`：执行摘要和全部本子目录产物hash。
