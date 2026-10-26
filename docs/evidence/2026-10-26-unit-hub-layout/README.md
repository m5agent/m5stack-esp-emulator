# HUB 附件布局与截图工具：推广后浏览器验证

2026-10-26，HUB 布局已按候选的精确两源 hash 推广；本归档的四项浏览器回归和
HUB 重放全部通过。**未启动 Device Service、QEMU、固件或物理硬件**。所有数值是
浏览器 fixture，不能作为 guest 消费输入、真实接线电气行为或固件功能证据。

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| Model shell | PASS：14主机模型、27 Unit 的 frame/input/output/lifecycle | [report](regression/model/report.json) |
| Unit panel | PASS：27 schema、22项检查、1440/1024/768/390 | [report](regression/panel/report.json) |
| Common bridge | PASS：31 POST、12可信pointer、完整高卡片与真实标题hit | [report](regression/bridge/contract-report.json) |
| Session mount | PASS：440×420→320×420，owned mount/dispose | [report](regression/mount/report.json) |
| 实际产品HUB重放 | PASS：13组检查，12图；after直接返回产品文件字节 | [report](regression/hub-product/report.json) |

执行前冻结36个命名源、202个vendor资产和2个执行harness，五项结束后全部无漂移；
最多同时运行2个浏览器。归档只复制预冻结tool-sources副本。runtime-profiles.json
是后续control15主机准入修改之前的batch快照，不能用未来字节改写本批来源。

## 布局与范围

只自动处理普通CoreS3 module（无DinBase）的直接grove→HUB，并允许直接紧凑
ENV III/ToF/Color/Button子附件；自定义unitPose、其他主机、其他Unit、更深HUB树
保留原布局。完整四档场景是ENV III@1、ToF@2、Color@3；Button只在390px作为
替换第一槽的交互/生命周期子例。其他排列、主机和固件没有继承PASS。

所有模型scale保持1，原始housing、sensor anchor、connector与控制hitbox保留。
三个完整附件在上方分开，HUB放在控制器左侧，官方UnitFrame/VisualCable API
仍连接两个真实口面。四档housing无互叠，LCD/宿主控制区和画布外16px rail无覆盖。
6144条实际线缆表面采样段零碰壳；故意恢复错误走线命中58次，恢复候选回到零。
这是明确场景的抽样几何检查，不是任意姿态、材料、制造配合或电气等效证明。

可选布局的snapshot、pose和恢复失败均隔离为unavailable，已完成附件不被dispose，
兄弟附件身份和位置保留，真实Button pointer仍到原路径。嵌套替换、detach/reuse、
stale async attach和整体dispose通过。额外annotation 17/17、P2恢复23/23通过。

**housing placement PASS，整体验收与手机总览触控舒适度仍PARTIAL。** 原生Button
pad在390px总览约23.76×19.07px，真实鼠标手势通过；既有公开focus路径放大后也
收到原生down/up。没有改默认camera fit、放大hitbox或新增产品focus控件；focus
子图只证明局部交互，不能用来声称整个场景始终完整可见。

## 截图工具修复与负控

common bridge改用CDP document clip，避免element screenshot在恢复页面顶部后
再次自动滚动，导致sticky导航覆盖标题；使用30秒deadline。最终正例PNG高1483px，
超过400px viewport，完整卡片和标题可见；capture_contract记录真实标题hit通过。
隔离旧bridge f982…的负控仍完成31 POST，并以0!==8的滚动位置断言预期失败；
其原PNG清楚显示sticky导航盖住标题。负控在读取可信pointer计数之前失败，不能把
最终正例的12次计数写入负控。负控只复制6个regular文件，
没有复制symlink树。两者均是浏览器fixture，没有guest执行。

先前root r1/r2是fixture margin期望和CDP裁切探索，原内部记录不覆盖。既有host9
等历史ENV截图的framing PARTIAL不倒改，也不以新截图替换旧证据。

## 来源与复现

- [汇总与边界](summary.json)
- [执行前freeze](source-freeze.json)
- [推广收据](promotion-receipt.json)与[最终11源cohort](promotion-cohort.json)
- [执行结果](run-summary.json)与[实际产品HUB harness](execution/browser-layout-product.mjs)
- [候选设计](candidate/DESIGN.md)、[patch](candidate/candidate.patch)、[历史manifest](candidate/manifest.json)
- [候选bbox](candidate/bbox-summary.json)、[最后12图检查](candidate/visual-review.json)、[r1-r9摘要](candidate/iteration-history.json)
- [原生读数contract](candidate/annotation-contract.json)与[P2恢复contract](candidate/frontend-recovery.json)
- [视觉复核](visual-review.json)与[公共脱敏记录](public-redaction-provenance.json)

candidate/保留promote前shadow历史，manifest.promoted=false是当时事实；推广收据
绑定内部原manifest hash，后面的真实产品回归单独证明实际返回的新module字节。
candidate公共manifest仅为绑定披露的token audit路径脱敏而更新该artifact hash，
内部原manifest、patch及receipt原件不变。公共副本的个人绝对路径改为<repo>/<home>，
每处前后SHA均披露。没有复制固件/ROM二进制或覆盖旧归档。

四个platform/tests入口可在仓库根目录向新输出目录重跑。HUB harness重放需要
历史候选静态base位于原.work路径；其after明确从实际产品目录读取，不允许把shadow
回放称为产品执行。执行harness、候选和本批source snapshot的层次应分别保留。
SHA256SUMS覆盖本归档全部文件（自身除外）。
