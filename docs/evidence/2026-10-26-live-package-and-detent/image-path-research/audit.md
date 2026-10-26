# UIFlow 图片路径静默失败：固定源码与已有同 guest 证据审计

日期：2026-10-26。只读研究；没有新增 guest、修改生产代码/固件/QEMU。

## 结论

当前已有同 guest 实验确认：同一张 PNG 的 bytes 输入能通过 drawImage 和 drawPng
各画出 24×24 的 576 个红像素，而绝对、相对路径四格均为黑色。因此本图已传输成功，
并且该 guest 的 PNG 解码/显示通路可以处理此图；不能把失败归为 PNG 数据损坏或普遍
不支持 PNG。

固定官方显示绑定中，存在确定的 **boxed length 错用**：把 mp_obj_len 返回的对象直接
cast 为 size_t，导致 ASCII 路径实际上限为 63 字符。当前实验绝对路径长 106，落在该
错误区间，与失败现象完全相符。相对路径另有绕过 LittleFS 当前目录拼接的源码缺口。
但没有针对当前 dirty 固件做符号级执行跟踪或独立 63/64 阈值测量，因此这些是已证实
存在于固定官方源码、能解释现象的原因，不能把每个源码分支均写成该 binary 已测执行。

## 固定来源

UIFlow commit：3a86d8f611b3639cca755a933e01a5a829771ef1。
其 gitlink 固定 MicroPython 78ff170de9e32c79db6e64d3e33d2bd60002bdcd，
M5GFX 9bcedf4e19d4cab7a0793de0598ae5390b4689fe，M5Unified
8530f5377d782e4a25a6c482de2e71c3f75ca8eb；见 official-gitlinks.json。
所有下载 URL、完整 SHA256、大小和本地文件名在 sources.json。

主要来源：

1. [实际 component 显示绑定](https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/m5stack/components/M5Unified/mpy_m5gfx.cpp)
   SHA256 b13f252dbfd05eaa9135169acb13c65766af7529973debdc45690e4e9ae853f7。
   已与缓存 2.5.3 文件逐字节比较，完全一致；见 cached-binding/binding-identity.json。
2. [实际 component LFS2Wrapper](https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/m5stack/components/M5Unified/mpy_m5lfs2.txt)
   SHA256 df1140a7df2064b7afa514a3d47546518631a110533ccb8d612af0ced42ace21。
3. [该 wrapper 委托的 VFS stream](https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/m5stack/_vfs_stream.c)
   SHA256 f4e1137727eeed88ce96ff1b2cf35721b0e4d23ffb59536ecfae35d8d7ab775b。
4. [同 commit 遗留 third-party wrapper](https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/third-party/cmodules/m5unified/mpy_m5lfs2.txt)
   SHA256 6fdbd9f82479d852a5d052f091fdd5aa107e8f70873d3d89661a2231e489d5a7。
   它是另一份实现，不能与实际 component 路径混算。
5. [M5GFX LGFXBase.hpp](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/lgfx/v1/LGFXBase.hpp)
   SHA256 e595198f2a0872c55a854b78d8a1d48cb656c534b62da183e4334f148afa01c1。
6. [M5GFX LGFXBase.cpp](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/lgfx/v1/LGFXBase.cpp)
   SHA256 c9bff4ce17f1e2127bf708ad6ebc9d10b4ac7bfed557340811cfea61769f9918。

## 绑定层与有效长度

- mpy_m5gfx.cpp:944 和 1028：
  `mp_obj_is_str(img) && ((size_t)mp_obj_len(img) < 128)`。
- MicroPython py/obj.h:90：repr A 的小整数对象是 `(n << 1) | 1`。
- py/obj.h:1076、py/obj.c:538-548：mp_obj_len 返回 mp_obj_t，而非裸整数。
- ports/esp32/mpconfigport.h:18：该固定 ESP32 port 使用 repr A。
- py/objstr.c:2062-2068：str 支持只读 buffer，返回底层字节及长度。

因此 ASCII 路径 n=63 对应对象值 127，通过 file 判断；n=64 对应 129，判断失败。
源码中的 128 不是正常裸长度限制。这里对 ASCII 路径作精确推导，不把 Unicode 字符数
与 UTF-8 字节数混用。

- drawImage:1032-1035 按路径末四字节识别扩展名；1053-1059 把 PNG 文件交给
  drawPngFile(wrapper, path)。
- drawImage:1062-1087 的 buffer 分支按真实前两字节识别 PNG/JPG/BMP；普通长路径
  转成 buffer 后通常以 '/' 等字节开头，未命中任何 magic，直接到 1090 返回 None。
- drawPng:944-961 同样分 file/buffer；长路径会被当作 PNG 内容交给解码器。
- 两种 binding 都丢弃底层 bool，最后恒定返回 None（drawPng:963、drawImage:1090）。

## wrapper、path_out 与当前目录

实际 component mpy_m5lfs2.txt:19-26 已委托 vfs_stream_open；本文件没有 128 限制。
它不是旧版直接在该文件内调用 mp_vfs_lookup_path 的实现。

现代 _vfs_stream.c:72-90 调 mp_vfs_lookup_path，并按 path 中的 flash/system/sd 字样
选择文件系统；106 直接把 path_out 交给 lfs2_file_opencfg。

固定 MicroPython extmod/vfs.c:57-96 定义：

- 绝对路径选择 mount 并去除 mount 前缀，path_out 仍是该卷内绝对路径；
- 相对路径只返回 vfs_cur 和原始相对 path_out，不拼接卷内 cur_dir。

正常 Python 文件打开会经过 extmod/vfs_lfsx_file.c:115-116 的 make_path；
extmod/vfs_lfsx.c:116-126 对相对路径拼接 self->cur_dir。现代 wrapper 直接调用
LittleFS C API，绕过这一步，因此 'assets/pixel.png' 不能仅因 os.chdir(package_path)
就等同于 package_path+'/assets/pixel.png'。

遗留 third-party wrapper:35-55 同样在 lookup 后直接 lfs2_stat/opencfg(full_path)，
也没有 cur_dir 拼接；同时强制把 mount 对象 cast 为 LFS2。此事实仅用于版本区别，
不声称当前 binary 一定使用这个旧分支。

现代源码另有 mode 缺陷：_vfs_stream.c:44-51 第47行用赋值覆盖第46行 READ。
wrapper:20 传 READ|WRITE，最终得到 LFS2_O_WRONLY，而不是 RDWR。
_vfs_stream.h:25-28 和 LittleFS lfs2.h:126-129 固定了这些位值。
但 LittleFS lfs2.c:3555 的读权限检查是 ASSERT；关闭 ASSERT 后未必阻止读取。
所以这是确定的源码问题，不能由此直接声称本次静默来自 BADF/权限失败。

## 已有六格实验的实际结果

从 image-path-diagnostic/evidence.zip 读取两路 serial、程序 source.json、PNG 与 frame；
ZIP CRC 通过，ZIP 内程序 bytes 与实际提交 main.py 一致。独立用 PIL 重算每格像素。
完整输入、长度、坐标、hash 在 observed-six-calls.json。

| 调用 | 实参 | 长度 | repr A 装箱长度 | 固定源码预测 | 实测红像素 |
| --- | --- | ---: | ---: | --- | ---: |
| drawImage | 绝对路径 str | 106字符 | 213 | buffer | 0/576 |
| drawImage | 相对路径 str | 16字符 | 33 | file | 0/576 |
| drawImage | PNG bytes | 97字节 | 不适用 | buffer | 576/576 |
| drawPng | 绝对路径 str | 106字符 | 213 | buffer | 0/576 |
| drawPng | 相对路径 str | 16字符 | 33 | file | 0/576 |
| drawPng | PNG bytes | 97字节 | 不适用 | buffer | 576/576 |

CWD 长 89 字符。PNG 为 24×24、8-bit RGB/color type 2、非交错，SHA256
77557fdbe0cf343aa10c373ee3a51e21df0a41a8dd56b4d9eb220b5bb8527d18。
frame 为 320×240，SHA256
0218f5688e03ce7f752600603df2ac1fef3a6433f08335618a4bbb06eeaab202。

serial.log 1993字节、serial1.log 0字节；两路都没有 vfs_stream_open 或 failed to open。
现代源码第68行虽有 INFO open 日志，但本轮缺少该日志，可能受实际实现/日志配置影响；
不能把“没有匹配”写成“没有尝试打开”，也不能据此证实相对路径的失败位置。

## 当前 binary 证据边界

四个已知 reference 固件的静态检查都命中现代 vfs_stream_open 与分配错误字符串，
没有命中旧 wrapper 的两条 printf；见 reference-wrapper-static-markers.json。
这支持现代函数已编入镜像，但不是某次 drawImage 调用实际使用哪个 wrapper 的证明。

已证实的是同一 guest 的四条字符串路径不画、两条 bytes 输入成功，以及 PNG/file hash
一致。绝对路径 boxed 长度错误和相对路径 CWD 遗漏是固定官方源码能解释现象的缺陷。
本任务没有新增 guest、阈值测试、短绝对路径别名、符号断点或固件修改。后续不能把这些
未执行项目写成 PASS；本块可使用显式文件读取 bytes 后调用既有绘图 API 的已测路径。

## 可归档文件

本目录只有文本/JSON/C/C++ 源码副本，不包含固件、ROM、compiler 或新 guest 产物。
保留 audit.md、sources.json、official-gitlinks.json、observed-six-calls.json、
observed-guest-source.py、reference-wrapper-static-markers.json、cached-binding/ 全部，
以及 sources.json 指向的固定官方源码文件。archive-files.json 给出逐文件 SHA256。
