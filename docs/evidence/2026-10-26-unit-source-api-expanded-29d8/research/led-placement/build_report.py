from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
VENDOR = REPO / 'platform/web/vendor/m5stack-models'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

manifest = json.loads((VENDOR / 'vendor-manifest.json').read_text())
paths = [
    'src/units/rgb/index.js', 'src/units/rgb/dimensions.js',
    'src/units/rgb/geometry-data.js', 'src/units/encoder/index.js',
    'src/units/encoder/dimensions.js', 'src/units/encoder/geometry-data.js',
    'src/units/shared/CADUnit.js', 'src/modeling/parts.js',
    'src/modeling/cad.js', 'src/core/Component.js', 'src/modeling/grove-cable.js',
]
files = []
for name in paths:
    actual = sha(VENDOR / name)
    expected = manifest['files'][name]['sha256']
    assert actual == expected, name
    files.append({'repo_path': str((VENDOR / name).relative_to(REPO)), 'sha256': actual,
                  'vendor_manifest_sha256': expected, 'unchanged': True})
dump('frozen-model-audit.json', {'schema_version': 1,
    'source_repository': manifest['source_repository'],
    'source_commit': manifest['source_commit'],
    'files': files,
    'unit_local_frame': {'view': 'from +Z toward origin, +Y upward',
                         'front': '+Z', 'back': '-Z', 'main_grove': '-Y',
                         'left_to_right': '-X to +X',
                         'scope': 'Unit local frame, not arbitrary browser camera or UnitFrame pose'},
    'sources': [
        {'file': 'src/modeling/parts.js', 'lines': [5, 30], 'fact': 'FACE front/back/top/bottom; Grove convention'},
        {'file': 'src/units/shared/CADUnit.js', 'lines': [7, 24], 'fact': 'main Grove at spec.grove.position, face bottom'},
        {'file': 'src/core/Component.js', 'lines': [25, 70], 'fact': 'component local positions assigned unchanged and mounted in host.body'},
        {'file': 'src/modeling/cad.js', 'lines': [6, 7], 'fact': 'CAD vertices attached unchanged to host.body'},
    ]})

# Only public official source receipts belong in this index. MCP records remain internal.
sources = []
for receipt in sorted(ROOT.glob('*.receipt.json')):
    item = json.loads(receipt.read_text())
    name = item['name']
    assert item['status'] == 200 and (ROOT / name).is_file(), name
    assert sha(ROOT / name) == item['sha256'], name
    assert 'mcp.' not in item['url'], name
    sources.append(item)
dump('source-index.json', {'schema_version': 1, 'sources': sources,
     'scope': 'Public official documentation, photos, CAD, and repository listings only; no MCP feedback or session metadata.'})

# Prove the current public images/STLs also match the frozen vendor provenance.
products = json.loads((ROOT / 'frozen-vendor-upstream-products.json').read_text())['products']
by_url = {source['url']: source for source in sources}
asset_matches = []
for product in products:
    for item in product.get('referenceSources', []) + product.get('structures', []):
        if item['url'] not in by_url:
            continue
        fetched = by_url[item['url']]
        assert item['sha256'] == fetched['sha256'], item['url']
        asset_matches.append({'sku': product['sku'], 'file': fetched['name'],
                              'sha256': fetched['sha256'], 'matches_frozen_vendor_source': True})
dump('frozen-source-asset-comparison.json', {'matches': asset_matches})

feedbacks = {}
for name in ('rgb', 'encoder'):
    feedback = json.loads((ROOT / 'internal' / f'mcp-feedback-{name}.json').read_text())['result']
    data = feedback['structuredContent']
    assert feedback.get('isError') is False and data['accepted'] is True and data['feedback_id']
    feedbacks[name] = {'submitted': True, 'topic': 'Missing PCB refdes-to-physical-position evidence',
                      'result': 'Accepted for official human review; no mapping supplied by this acknowledgement'}

findings = {
 'schema_version': 1,
 'date': '2026-10-26',
 'status': 'RESEARCH_COMPLETE_WITH_OPEN_EVIDENCE_GAPS',
 'scope': ['Unit RGB U003', 'Unit Encoder U135'],
 'mutations': {'product_source_modified': False, 'vendor_source_modified': False,
               'adapter_modified': False, 'frozen_harness_modified': False,
               'device_service_calls': 0, 'runtime_or_qemu_started': False,
               'output_scope': '.work/unit-led-placement-research-20261026/'},
 'evidence_level': 'Official-source documentary research only; no virtual-device run or hardware measurement',
 'model_freeze': {'source_commit': manifest['source_commit'], 'audit': 'frozen-model-audit.json'},
 'products': {
  'rgb': {
   'sku': 'U003', 'mapping_status': 'OPEN',
   'electrical_cascade_order': ['LED3', 'LED2', 'LED1'],
   'electrical_source': 'rgb-schematic.png',
   'electrical_scope': 'Cascade adjacency only; no new connector-net or physical-placement conclusion',
   'visual_components': {'led0': [-6.5, 2.7, 4.03], 'led1': [0, 2.7, 4.03], 'led2': [6.5, 2.7, 4.03]},
   'main_grove': [0, -15.65, 0], 'out_grove': [0, 15.65, 0],
   'electrical_chain_position_to_visual_id': {'first_LED3': None, 'second_LED2': None, 'third_LED1': None},
   'confirmed_observation': 'Official assembled-product photos and drawing show three front light apertures; no inspected source shows readable LED1/2/3 placed on an oriented PCB.',
   'inspected_product_photos': ['rgb_01.webp', 'rgb_02.webp', 'rgb_03.webp', 'rgb_05.webp', 'rgb_06.webp'],
   'hardware_repository_inventory': ['Products/U003_Unit_RGB/Structures/Unit_RGB.stl'],
   'blocker': 'No reviewed assembly drawing, PCB/Gerber silkscreen, or oriented front/back photo connects LED1/2/3 to physical left/center/right.',
   'feedback': feedbacks['rgb'],
  },
  'encoder': {
   'sku': 'U135', 'mapping_status': 'OPEN',
   'electrical_cascade_order': ['U2.PA0', 'LED1', 'LED2'],
   'electrical_source': 'encoder-schematic.webp',
   'visual_components': {'led0': [-7.5, 7, 5.9], 'led1': [7.5, 7, 5.9]},
   'main_grove': [0, -15.65, 0], 'knob_press': [0, 7, 6], 'knob_axis': [0, 0, 1],
   'protocol_index_to_visual_id': {'1': None, '2': None},
   'refdes_to_physical_side': {'LED1': None, 'LED2': None},
   'confirmed_observation': 'Official U135 bare-PCB photo shows the two LED packages flanking the main Grove at the connector end. LED1/LED2 reference designators are not readable.',
   'photo_orientation': {'file': 'encoder_03.webp', 'size_pixels': [800, 800],
      'view': 'encoder shaft/component side, Grove downward',
      'approximate_pixel_landmarks_for_navigation_only': {'knob_center': [398, 290], 'grove_center': [397, 576], 'left_visible_led': [291, 552], 'right_visible_led': [500, 553]},
      'interpretation_limit': 'Pixel landmarks are navigation aids, not dimensions, metrology, refdes identification, or hardware validation; PCB revision not legible.'},
   'qualitative_model_observation': {'status': 'DOCUMENTED_FOR_FOLLOW_UP_ONLY',
      'official_photo': 'encoder_03.webp',
      'frozen_source': 'platform/web/vendor/m5stack-models/src/units/encoder/index.js:10',
      'photo_relation': 'Both LEDs at Grove flanks, on the connector side of the mounting-hole waist; rotary shaft is at the opposite end.',
      'frozen_model_relation': 'Both LED centers at Y=+7, the same Y row as the knob; main Grove center at Y=-15.65.',
      'conclusion_limit': 'A qualitative location discrepancy in these frozen source coordinates versus the documented U135 photo; no physical left/right electrical index inference, no exact corrected XYZ, and no geometry/current functionality conclusion changed.'},
   'inspected_product_photos': ['encoder_01.webp', 'encoder_02.webp', 'encoder_03.webp', 'encoder_05.webp', 'encoder_06.webp'],
   'supporting_back_photo': 'encoder-firmware-01.jpg',
   'hardware_repository_inventory': ['Products/U135_Unit_Encoder/Structures/Unit_Encoder.stl'],
   'blocker': 'No reviewed oriented PCB source labels the two visible LEDs as LED1 versus LED2; schematic symbol left/right is not placement evidence.',
   'feedback': feedbacks['encoder'],
  }
 },
 'next_evidence_needed': [
    'Obtain SKU- and PCB-revision-bound assembly placement drawing or top/bottom Gerber silkscreen with readable LED reference designators and Grove orientation.',
    'Alternatively obtain original front/back photographs with readable reference designators, the same board orientation, and the actual board revision.',
    'Only after independent review fill index-to-visual mapping; document any purely mechanical location correction separately from electrical-order calibration.',
    'Keep current electrical-order swatches until the physical mapping gate is met. Do not infer mappings from schematic symbol order, visual id numbers, wire routing, or another SKU.'
 ],
}
dump('findings.json', findings)

report = '''# U003 / U135 LED 物理位置证据研究

日期：2026-10-26。范围仅为 Unit RGB U003 与 Unit Encoder U135。

**结论：两个“电气索引/位号 → 物理 LED/可视组件”映射仍为 OPEN。** 官方原理图确认级联关系，但本轮检索和复查没有取得可同时核对 LED 位号、板版本与观察朝向的 PCB placement/Gerber/丝印证据。不以编号、原理图符号左右或其他 SKU 补全。

本报告是官方资料研究，不是 virtual-device PASS 或 hardware validation。未修改 vendor、adapter、功能代码、冻结测试输入或现有模型结论；未调用 Device Service、未创建 session、未启动 QEMU。全部产物保存在本研究目录。

## 冻结模型与观察坐标

本地 vendor 对应 `https://github.com/yuyun2000/m5stack-models` 的 `48ab992f5ff63c1a91296051e1afcb5959877903`。11 个相关源文件实际 SHA256 与 vendor-manifest 声明逐一相等，见 [冻结模型审计](frozen-model-audit.json)。这只证明研究读取的源与冻结输入一致。

统一使用 **从 +Z 看向原点、+Y 朝上** 的 Unit 本地视角。`front=+Z`，主 Grove 沿 `-Y` 向下，屏幕左到右对应 `-X→+X`。依据为 `src/modeling/parts.js:5,21-30`、`src/units/shared/CADUnit.js:14`、`src/core/Component.js:25-37,68-70` 和 `src/modeling/cad.js:6-7`。浏览器相机和 Grove `UnitFrame` 的额外姿态可能改变最终屏幕左右，不能直接拿屏幕左右当本地坐标。

| 型号 | 组件 | 冻结 Unit 本地坐标（mm） | 源文件行号 |
| --- | --- | --- | --- |
| U003 | `led0 / led1 / led2` | `[-6.5,2.7,4.03] / [0,2.7,4.03] / [6.5,2.7,4.03]` | `src/units/rgb/index.js:8` |
| U003 | 主 Grove / `out` | `[0,-15.65,0] / [0,15.65,0]` | `rgb/dimensions.js:16-23`；`rgb/index.js:8` |
| U135 | `led0 / led1` | `[-7.5,7,5.9] / [7.5,7,5.9]` | `src/units/encoder/index.js:10` |
| U135 | 主 Grove | `[0,-15.65,0]` | `encoder/dimensions.js:16-23` |
| U135 | 按压/旋钮轴 | `[0,7,6]`；轴 `[0,0,1]` | `encoder/index.js:8-9` |

## U003：只闭合级联关系，未闭合左中右

[官方原理图原图](rgb-schematic.png)可核对 LED3→LED2→LED1 的逐级 DOUT/DIN 关系。本轮只复述这三颗器件的级联邻接，不新增 J1/J2 输入网络解释，也不把原理图摆放当作 PCB 放置。

逐张查看 [官方主图](rgb_01.webp)、[背面图](rgb_02.webp)、[包装图](rgb_03.webp)、[装配图](rgb_05.webp)、[正面比例图](rgb_06.webp)及[尺寸图](rgb-size.png)。装配图可见三个正面透光孔和两个 Grove；它们没有展示可读 LED1/LED2/LED3 位号的裸 PCB。

当前官方 `M5_Hardware/Products/U003_Unit_RGB` 只有 `Structures/Unit_RGB.stl`，目录原始回执见 `github-rgb-contents.json` 与 `github-rgb-structures.json`。STL 是结构网格，不携带器件电气位号映射。补查官方 `M5Unit-RGB` 完整树及 `unit_RGB.hpp`，只确认三像素定义，没有取得 PCB 位号放置资料。

因此 `LED3/LED2/LED1 → led0/led1/led2` 的任何排列都未获本轮证据批准。`findings.json` 中三项映射均保持 `null`。

## U135：确认 Grove 两侧有灯，LED1/LED2 左右仍未知

[官方原理图](encoder-schematic.webp)给出 `U2.PA0 → LED1 → LED2`。协议的索引选择不能独立证明物理左右。

关键证据是官方 U135 页面引用的裸 PCB 原图：[encoder_03.webp](encoder_03.webp)。以旋钮轴/元件面朝向观察者、Grove 向下观察，两颗 LED 在 Grove 左右两侧、安装孔收腰的连接器一端；旋钮轴在另一端。该图没有可读的 LED1/LED2 丝印，PCB 版本也不可读，所以不能把左侧或右侧命名为 LED1/LED2。

![官方 U135 裸 PCB 原图](encoder_03.webp)

原图为 800×800。仅为方便复核，旋钮中心约在 `(398,290)`，Grove 中心约 `(397,576)`，两颗 LED 中心约 `(291,552)` 与 `(500,553)`。这些像素标记不用于毫米尺寸、光学/机械测量或电气位号推导。

对比冻结源码：两个可视 LED 均在 `Y=+7`，与旋钮的 `Y=+7` 同行，主 Grove 则在 `Y=-15.65`。**官方照片的“Grove 两侧”与当前冻结源的“旋钮同行”存在定性位置差异，可作为后续模型复核线索。** 本轮不提出精确修正 XYZ，不修改几何，不用该观察推 LED1/LED2 或协议 index 1/2 的左右，也不改变现有功能/几何结论。

另逐张复查 [主图](encoder_01.webp)、[背面图](encoder_02.webp)、[装配图](encoder_05.webp)、[另一侧装配图](encoder_06.webp)、[尺寸图](encoder-size.png)，并查看官方固件仓库的[背面 SWD 接线照片](encoder-firmware-01.jpg)。后者同样没有闭合 LED 位号。

当前 `M5_Hardware/Products/U135_Unit_Encoder` 仅有 `Structures/Unit_Encoder.stl`。`M5Unit-Encoder` 驱动树与 `M5UnitEncoder_Firmware` 的 docs 树没有 PCB/Gerber。未下载或运行固件 HEX。

## 后续最小可实施路径

1. 取得绑定 SKU 与 PCB revision 的 assembly/placement drawing，或包含 Top/Bottom silk 的 Gerber；需同时读出 LED 位号和 Grove 朝向。
2. 也可使用同一板版本的清晰正反面原始照片：位号、Grove、旋钮/透光面方向必须能交叉复核。照片缺位号时仍保持 OPEN。
3. 独立审阅后再补“电气索引→可视组件”映射。纯机械位置修正与电气顺序标定分别保留依据；不能以一项代替另一项。
4. 在这之前继续使用明确标为电气数组顺序的 swatch，不把未确认颜色投射到实体灯位。

按照 `m5stack-assistant` 技能要求，已对 U003、U135 各提交一项“缺少 PCB 位号到物理位置资料”反馈，官方返回接收成功；这不构成映射证明。请求、返回和反馈标识仅保留在 `internal/`，不进入公开来源清单。

## 证据与复核

- [结构化结论](findings.json)：映射状态、空映射、坐标、照片朝向、后续门槛。
- [公开来源清单](source-index.json)：源 URL、最终 URL、抓取 UTC 时间、HTTP 状态、字节数、SHA256；不含 MCP/反馈会话。
- [冻结模型哈希](frozen-model-audit.json)：11 个相关源文件均与 vendor manifest 一致。
- [冻结公开素材比对](frozen-source-asset-comparison.json)：本轮抓取且可在冻结 source-manifest 中对应的素材 SHA256 逐一相等。
- `check_evidence.py`：重新校验下载字节、冻结文件、素材绑定和 OPEN/null 门槛，不触发 API、运行时或网络。
- `SHA256SUMS`：公开研究产物的字节摘要；`internal/` 独立保留，不在该清单中。

本轮范围内，未发现足以把任一映射从 OPEN 改为确认的资料。
'''
(ROOT / 'report.md').write_text(report, encoding='utf-8')
print(json.dumps({'sources':len(sources), 'frozen_files':len(files), 'asset_matches':len(asset_matches),
                  'mapping_status':{name:data['mapping_status'] for name,data in findings['products'].items()}},ensure_ascii=False))
