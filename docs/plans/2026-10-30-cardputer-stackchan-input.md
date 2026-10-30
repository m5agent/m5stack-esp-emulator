# Cardputer-ADV 输入/方向与 StackChan 运动中触摸

日期：2026-10-30。基线为远端 main `e3f149c1`，已含 PR #30 与 #39。

## 目标与约束

验证 Cardputer-ADV 的真实键盘事件进入原固件 API，显示驱动的横屏/竖屏及旋转
不丢失局部绘制；验证 StackChan 舵机连续运动期间，屏幕 FT6336U 输入与固件
触摸处理保持独立。顶部 Si12T 不能替代屏幕触摸。

沿用独立 managed worktree；不覆盖主 checkout 的用户未提交资产，不访问或
停止用户 8787/8830 服务及无关会话。原始固件、日志、帧与运行响应只留 `.work/`。
普通测试不得依赖这些本机缓存，公开摘要保留精确身份和失败。

## 执行边界

- Cardputer：先审合并后的 Qcode、TCA8418/旧 GPIO 路由和 MADCTL/窗口方向；
  用逐键、修饰/组合/松开及四种旋转下的非对称图案和局部绘制建立 guest 证据。
- StackChan：先以真实模型点击复现运动后的屏幕命中和坐标，再用同一固件的
  舵机实际位置、FT6336U 控制器与原 Touch API/帧读回验证。阻塞舞步与主动
  轮询分别测试，不能把示例不轮询说成硬件互斥或通过网页伪造触摸响应。
- runtime：合并后的 65-patch 锁没有匹配的既有 WASM；在独立目录重建全部
  QEMU 对象，校验补丁/源码/依赖、构建回执及导出来源，再做单实例浏览器验证。
  既有分支二进制、旧 Pages 或 native 结果均不能替代本次浏览器 PASS。

## 完成条件

每条结果精确绑定 source/runtime/profile、固件 SHA、真实输入与串口/帧/控制器
状态；保存正常 Stop 和 context.close 前 Worker 清场结果。保持 virtual-device
与 physical hardware 分开。更新当前状态、唯一 Backlog、台账和生成快照；
通过窄测、相关平台契约和 diff/隐私检查后按既有 PR/预览交付流程收尾。

## 结果与交付范围

Cardputer 的原 IRQ reader、56 物理键、PC 修饰与四旋转/局部刷新已有独立浏览器
证据；StackChan 默认示例的同步工作饥饿已有失败计时，真实 UART 后台线程版
恢复运动中约 100/300/800ms 的屏幕点按。原 Arduino BSP 的并行与不轮询负控
也完成，首例普通 Stop 的 engine target 延迟回收保持 PARTIAL，不以后续成功覆盖。
收尾已合并 main `ccbfa71c`；V5 只含两份 Core2 元数据差异，WASM、生产 Web 和
固件字节保持一致，再按最终包复核。精确身份、失败、命令入口和发布结果统一见
[本轮证据](../evidence/2026-10-30-cardputer-stackchan-input/README.md)。
