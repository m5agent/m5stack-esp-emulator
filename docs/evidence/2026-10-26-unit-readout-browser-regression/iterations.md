# 历史迭代与失败边界

本页只概述内部.work的早期尝试，不复制失败日志、个人路径或旧截图。最后四项
promoted-source回归分别一次完成，不意味着候选研发从未失败。

- 最初overlay：修复harness window-id冲突，并明确公开setView(0)仍需下一render
  settle；nested三卡贪心布局曾隐藏第三项。修复后卡片仍挡宿主，视觉保持PARTIAL。
- rail首轮：frozenDefinitions门在shell adapter中漏透传，明确显示契约不可用，
  未输出默认值；补齐透传后重新运行。
- 最终rail：四个数据/ACK负向边界和Thermal双来源逐项修复。最后browser-only
  15项PASS/12图；独立contract最终17项PASS。
- rail卡片遮挡已关闭；nested本体互叠仍独立OPEN，不升级为完整几何/物理PASS。

旧失败尝试的内部原件全部不变；公共归档只保留此摘要与最终可复核证据。
