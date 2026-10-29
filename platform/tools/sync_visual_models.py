#!/usr/bin/env python3
"""Vendor a reviewed public m5stack-models Git commit, never its dirty worktree.

Usage: python3 platform/tools/sync_visual_models.py --source /path/to/public/repo
Use --commit FULL_SHA to review a newer snapshot; --check verifies without writes.
Only runtime JavaScript, explicitly reviewed product sticker PNGs, public
metadata, redistribution notices and exact reviewed public guide texts are
allowed. Private research, raw CAD/photographs, demo and dependencies are not copied. Node parses ESM dependencies without
executing upstream code before any snapshot is written.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import posixpath
import re
import subprocess
import tarfile
import tempfile
import urllib.request
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "platform/web/vendor/m5stack-models"
RUNTIME_DEVICE_CATALOG = ROOT / "devices/catalog.source.json"
PINNED_COMMIT = '4879ab51eb8bb11ce024e670ae6880529e3d0f42'
PUBLIC_REPOSITORY = "https://github.com/yuyun2000/m5stack-models"
REVIEWED_LOCAL_RUNTIME_PATCHES = ({
    "id": "device-viewer-pause-rendering-v1",
    "source_commit": PINNED_COMMIT,
    "target": "src/core/DeviceViewer.js",
    "upstream_sha256": "ef10a9f80d618b6d70fb147c65735916ef68b0865ff307beccd501a9fc7be70d",
    "effective_sha256": "2d6a70f3fe06a106eba19d78b4bcfb056e5244f4539cd4e3ceb6e57c92174657",
    "patch": "patches/visual-models/0001-device-viewer-pause-rendering.patch",
    "patch_sha256": "0a0f5c9f16f350370175740f1c662d1d6a52f1e0d2d5661a163f2ddb9382acb1",
    "adapted_from": {
        "repository": "https://github.com/m5agent/m5stack-esp-emulator",
        "commit": "3de27e88edf4e8897f8408c5f6b82ef2b881d421",
        "path": "platform/web/vendor/m5stack-models/src/core/DeviceViewer.js",
        "sha256": "fc32ef6e6acb328403d08450b0d503fdcda09d9437b4c393457ab7797d11eda4",
    },
    "scope": "Preserve mainline boot-time pause/resume/dispose rendering on the upstream hidden-viewport fit fix; no model, resource or firmware admission changes",
},)
THREE_ADDON = "examples/jsm/utils/BufferGeometryUtils.js"
THREE_DESTINATION = ROOT / "platform/web/vendor/three/addons/utils/BufferGeometryUtils.js"
THREE_ADDONS = {
    THREE_ADDON: THREE_DESTINATION,
    "examples/jsm/geometries/DecalGeometry.js":
        ROOT / "platform/web/vendor/three/addons/geometries/DecalGeometry.js",
}
RASTER_SOURCE_COMMIT = PINNED_COMMIT
# Guides remain a separately reviewed documentation snapshot. New visual models
# do not pull upstream raw/browser evidence into this source distribution.
GUIDE_SOURCE_COMMIT = '3681a6482aff96501d44659ba5a1603246f1fe1f'
RASTER_NOTICE_SHA256 = '955a8b63544ca1816c4f59e6d91775ea265cb56fe98fab4f68c544448a4989fd'
# Exact public Git objects reviewed with the provider-permission notice above.
# New source commits/assets require an explicit review of this allowlist.
REVIEWED_RUNTIME_PNGS = {'src/devices/atom-echo/artwork/compliance.png': 'e065c851da4496ef789cad6e56e2f69fd6dd8d1be858994a08ba016fca31ffcf',
 'src/devices/atom-echo/artwork/rear.png': '046bb3eceb8b6f046e7f1540feb98726540ae46b348a337a5f19a1d54cd1699b',
 'src/devices/atom-echos3r/artwork/compliance.png': '707a79a7c5a196688a851212974c9bccb20ba3d2a67ee5537b562fe7e93c8886',
 'src/devices/atom-echos3r/artwork/rear.png': 'bf0bf751cac84b5ec3287efb83cd3ab606419420b8574216acb6c4a5dca4ea92',
 'src/devices/atom-lite/artwork/bottom.png': '3f95fcdb3e2d4f048418b2264ad8514f5af624ad216f1a2e3b112d8f6a5b86f5',
 'src/devices/atom-lite/artwork/compliance.png': '3a7661a742eeebb012e5be6f7276c0255cdd7875042d0da916abc3fca87c734a',
 'src/devices/atom-matrix-v11/artwork/compliance.png': '7fed7bde77281d09ccab2f957f1e38db4aaae2319eaf3077e47ff78bd09e3598',
 'src/devices/atom-matrix-v11/artwork/rear.png': '9225a657a5b1d44248cb064ababf327390e07d696bf701abc851ba3f11ca4a4b',
 'src/devices/atom-matrix/artwork/compliance.png': '753400d885ee1b4aca284204a8203eacff6dfebfe22ffde65225749e931411a0',
 'src/devices/atom-matrix/artwork/rear.png': 'e605b10db38874727fe42a40f0e97285513cbaaa1cfe5f913c7a1f10034beb48',
 'src/devices/atoms3-lite/artwork/bottom.png': 'e75498e292397fc4f4a141dde6db3ec23c572407d5a32005fc3e9a6307204ca3',
 'src/devices/atoms3-lite/artwork/compliance.png': '271e0911cf7f079259b3310f603f5898277d7d22474574e7daf0611e88995ba3',
 'src/devices/atoms3/artwork/compliance.png': '015882d3cc887941d1d9cf7f67baa0f99d38883239a5e80ee3544312b1e15ac6',
 'src/devices/atoms3/artwork/lcd-flex.png': '9d96b3b3de0068e491491cf428f30504763ff7e9eea43789bd5ee99576270817',
 'src/devices/atoms3/artwork/rear.png': 'a18bb78ef6562276e30fbf9e7dcda26eafb203b467094305e30e79c5fc1172d5',
 'src/devices/atoms3r-ai-chatbot/artwork/base-bottom.png': '98d08ebfd31da46dea0ad568a263a3e9149f09f9b651dd33aca0c9c235c87d4f',
 'src/devices/atoms3r-ai-chatbot/artwork/base-front.png': '7e3dab4ca7512bb7b9cc165390c4a2beaa1640405795e6cb6e8d6e61558674f8',
 'src/devices/atoms3r-ai-chatbot/artwork/base-mic.png': '4be8ad8f1c60a5e51001081629f91e554ee7637b4fa179725cddce8ae61eafce',
 'src/devices/atoms3r-cam-ai-chatbot/artwork/base-bottom.png': '98d08ebfd31da46dea0ad568a263a3e9149f09f9b651dd33aca0c9c235c87d4f',
 'src/devices/atoms3r-cam-ai-chatbot/artwork/base-front.png': '7e3dab4ca7512bb7b9cc165390c4a2beaa1640405795e6cb6e8d6e61558674f8',
 'src/devices/atoms3r-cam-ai-chatbot/artwork/base-mic.png': '4be8ad8f1c60a5e51001081629f91e554ee7637b4fa179725cddce8ae61eafce',
 'src/devices/atoms3r-cam/artwork/camera.png': 'ccef95d89402f1fd4c5391e628dff16720157f7905a26219d438059c7c0fb049',
 'src/devices/atoms3r-cam/artwork/compliance.png': '367c665e8f431bbe568b7385f29705dc8d9d38d2cd31d759ee3369c8514d5ceb',
 'src/devices/atoms3r-cam/artwork/rear.png': '934f223edcceeb953888fd303edaab10fd5bb30d23f5787c1d69b008c8299f7c',
 'src/devices/atoms3r-ext/artwork/compliance.png': '5c8aad0cb8abad5066592b9263f12d1dd2d783943b8bf68fc51fc8925f348aba',
 'src/devices/atoms3r-ext/artwork/prototype.png': 'c00353796de37f9e5434c8470c6a2906781b21cb9cfaca2bcf259cad7a1c0c46',
 'src/devices/atoms3r-ext/artwork/rear.png': '6bf6c7e2b6675b2163791cb9bbc2e12db1ddd81f7b736e4b3f2fa489e89d8778',
 'src/devices/atoms3r-m12-volcengine-kit/artwork/base-bottom.png': '98d08ebfd31da46dea0ad568a263a3e9149f09f9b651dd33aca0c9c235c87d4f',
 'src/devices/atoms3r-m12-volcengine-kit/artwork/base-front.png': '7e3dab4ca7512bb7b9cc165390c4a2beaa1640405795e6cb6e8d6e61558674f8',
 'src/devices/atoms3r-m12-volcengine-kit/artwork/base-mic.png': '4be8ad8f1c60a5e51001081629f91e554ee7637b4fa179725cddce8ae61eafce',
 'src/devices/atoms3r-m12/artwork/compliance.png': '16ee6368326da6a1a72f1e637901b42d87c393c82a35fddf91ce37e57bc92e27',
 'src/devices/atoms3r-m12/artwork/rear.png': '00b9ab901fabdd49a2fafd6bc5831eccbf6fed7abd97a384acc778dc7d4a6634',
 'src/devices/atoms3r/artwork/certification.png': 'a8c9adb7c4d0675c47584cbd6a9c3762fbf943bbc0366093a5c6f8ea348e1990',
 'src/devices/atoms3r/artwork/rear-main.png': 'f4559ab19c552641a26ee56d96cb52700afe1a28af1e6dd5f75617fb15b0e463',
 'src/devices/atoms3u/artwork/rear.png': '203e6fcb7414cd041a43298f088ba8759ffcf50785536e5caed61471a623db2d',
 'src/devices/atomu/artwork/rear.png': 'ac788ead6873d3a92825fcecc0c3609736d36eb1dcdc89cb4f7c5a2d2b8f3a3a',
 'src/devices/basic-v27/artwork/pcb.png': '4796431e86b8a83fb26658f704684452a8b102cccfb9a37005f741f0e5ec625b',
 'src/devices/basic-v27/artwork/rear-bottom.png': '4ea21063b8bcfdf0ee61e9adf1eb0e6d45348c8b128d7c5d2464819dacf7c087',
 'src/devices/basic-v27/artwork/rear-left.png': '4dc63dea6d9a231d43f9d6997f8790c60d6a51fa47b71ab8af329c777464f2c8',
 'src/devices/basic-v27/artwork/rear-right.png': 'fbdc5577a9d51e92d19d978343011eff2d76cbaea637df8c18201b62138a74bc',
 'src/devices/basic-v27/artwork/rear-top.png': '183e75126f95bec836ee56ae2524db39ad5973ab5f29013f56d0274f2e7c88a8',
 'src/devices/cardputer-adv/artwork/back.png': 'd35128e9e158873df01d32d31bd230c20a5135fc6074ef3cfa4083e19f1db1ca',
 'src/devices/cardputer-adv/artwork/front-name.png': '05062fdb2753812e0e281fe0d8a5148ea2658f69d85548b9f46ac1bdd6dae431',
 'src/devices/cardputer-adv/artwork/grove-side.png': 'b6f7df4b1aad2d7125b6fe9da21acbea329d8a766396bed9aff645ddf1da1f0a',
 'src/devices/cardputer-adv/artwork/keyboard-1.png': '07de8cebb19269bf8222dde0f7d15b285fcf7d6ca5fdd4c648f584dbbac10ef1',
 'src/devices/cardputer-adv/artwork/keyboard-2.png': '39404c232bd18847336309433d244d46976a02f274ade962656f9196896a35ed',
 'src/devices/cardputer-adv/artwork/keyboard-3.png': '7f31707a98c8ca7bd22aff847a6abbdea0e67ab6f880b7c0d96682281b33e385',
 'src/devices/cardputer-adv/artwork/keyboard-4.png': '7e526f3f1a75b66a6ae49490b256050b9d5041fbb5c4cfd23c423dd69e011cf3',
 'src/devices/cardputer-adv/artwork/stamp.png': '3bd22b202861c24d994cfe3e309a67d924dc7dddd5eec39883efbb7636bba2eb',
 'src/devices/cardputer-adv/artwork/top-edge.png': '79d221d5c1ea1092923d3a932c95ea420790d5842340194b435b6cc51da946c3',
 'src/devices/cardputer-zero/artwork/front-power.png': '8b829e506d97828057147351adf83beed072f5d3b4ca5f7e6d03bafb88749af8',
 'src/devices/cardputer-zero/artwork/front-zero.png': '489c5c27f986d6d6e26cd3821b7c146636407ec5c9aea6cd670bfbd96d17ee0a',
 'src/devices/cardputer-zero/artwork/keyboard-row-1.png': 'ff7e31185eaf49f1127a31338ed34725d761eddaeab9e692ba891a437fd97251',
 'src/devices/cardputer-zero/artwork/keyboard-row-2.png': 'bf954658f1a22ac9fa95e3bd0e858359598d3a1480426276dd6b9d38e3f73704',
 'src/devices/cardputer-zero/artwork/keyboard-row-3.png': 'cb993cb8b43154550afd63f2f21c875e2dfd1e9a76a340e29ca5f34ab653ec4a',
 'src/devices/cardputer-zero/artwork/keyboard-row-4.png': '732f15a185a099644c734d9990b74b51356161ded9029abc222e35b27d06938f',
 'src/devices/cardputer-zero/artwork/left-usb-network.png': 'fcd3118034f9ee410f33a5f51caf9d7a5f3a1996dedff03e573058bae11fb5df',
 'src/devices/cardputer-zero/artwork/power-cap.png': 'b6abc5f604c8dd3adf18905c5883c7727f925234ccb0c3812fcfc0fb67e35fd8',
 'src/devices/cardputer-zero/artwork/rear.png': '20236e5a18199ac9cee26a82efcd7ddf7f5e2786354642821ae8553b42141730',
 'src/devices/cardputer-zero/artwork/right-display-audio-grove.png': '0ce068068b7907f90cecb421d8b7975198fdd0988881b976e10b1b3700bb22d4',
 'src/devices/cardputer-zero/artwork/top-gpio.png': 'fc31f3d3f4b4335209b9cba03a94eee00831ac52887608789359d1092359e4ca',
 'src/devices/cardputer-zero/artwork/top-sd.png': '673d71cafe58a14d8ee7a3a2f8ec9ae1e3bc84320b94e5a820c4b10feadd3fa9',
 'src/devices/core2/artwork/certification.png': 'b3bf157041cedfd8efcf4b623b2b61033e6dd2542ce4d6d7882bb497f2fcdd81',
 'src/devices/core2/artwork/rear-main.png': '6861115ae897d09c28bdcfa66d0366e1a98b54d19daf2379d12e157369dc478d',
 'src/devices/core2/artwork/reference-redraw-ext.png': '76c8cee2c43a0ec9a533a78c4d155ffd2949537d33f6b9c507deccdabc29ffea',
 'src/devices/cores3/artwork/certification.png': '964e5b906bc2e9d91c6ece331089bee131b1c662471234fe2260d0fa83d002c7',
 'src/devices/cores3/artwork/din-dc.png': '4e91a6d58842571519bed3cafcf25cea8c449c6d8b89e8f5eb3d8b6e353ef66c',
 'src/devices/cores3/artwork/din-name.png': '9e60e39962f93773f0da8e28e907912e35dc2ecc1801f0e4df4dc5499fec7e9c',
 'src/devices/cores3/artwork/din-power.png': 'ed376ff64f00f504a442f0accf7c7b3378464deebf862cd85d5babc41b583c01',
 'src/devices/cores3/artwork/port-b.png': 'f930e559e994c0e9488828c9831ac03bbcf9962279fa79582beec9a16d622ec8',
 'src/devices/cores3/artwork/port-c.png': '9244524465e35a8d870192641653c636f4c55237725e43a2ac21bd30c24f6154',
 'src/devices/cores3/artwork/rear.png': '8663eeb85a1b09d6564d8cc1ac60cce8ec7fd1a0f8de9e95103cc2e7da3e9d15',
 'src/devices/cores3/artwork/reference-redraw-din-pcb.png': '1d05fc40067f5f7d7c37777e1bf88cc92b40b6f7afa906aebfeb2ef0f3f5b267',
 'src/devices/dial/artwork/stamp-label.png': '212c32eef6f17d2e15d8a4e063751e4c4e85b871780b237283548fbf13059274',
 'src/devices/m5stick/artwork/rear-gray.png': 'ef0cef7be23f53cb9a14ad32ec8ce98e0d2a4d02813d686f80cf7ffcf7447a30',
 'src/devices/m5stick/artwork/rear-white.png': '60ef5670fe76b0325e914582366c1fabb8daac0d3128ecefe5173a0a3e765a8f',
 'src/devices/nanoc6/artwork/reference-redraw-ce.png': '894a432552847c0e1b8ab322fd3a6e4764cf045f6f9a25dc252b7be7b85e4556',
 'src/devices/nanoc6/artwork/reference-redraw-rear.png': '7c1f827b1947a4f6a3a9e48a921dd7a5e15c6c749b9734e1ffc9392e2760d860',
 'src/devices/nanoc6/artwork/reference-redraw-weee.png': 'd1e751c181d1943c4f1b0d8141f14ff9ac00e290a1f5809d035f2184deb6635a',
 'src/devices/nesso-n1/artwork/reference-redraw-antenna.png': 'e5cd9db9292dde90b4d717cbd149a9bbf4500a0c1d3c6961b7044ab55038c66a',
 'src/devices/nesso-n1/artwork/reference-redraw-qwiic.png': '40b0bd7ee4ae4d72e8e9395cde920b31d89c8c90fcb5d0ba690e0cd2352b86c2',
 'src/devices/nesso-n1/artwork/reference-redraw-rear.png': '22479a68a3cdced2c04266d55ba8ac45e0681efceecd4b60e0a4b648df733581',
 'src/devices/nesso-n1/artwork/reference-redraw-top.png': '3a5e0eaf55ea3ca5ce0ba54586f2348058c66f68a80428699848513deaf98001',
 'src/devices/papercolor/artwork/bottom.png': 'ea59298cba7f6222a42783f84de57a5dbef9b90c6ea47df768afe88f468c696c',
 'src/devices/papercolor/artwork/rear-lower.png': 'b0839c0a100c3e67562a551aa372768047849a36c2a1e6f80871dbe437da6cae',
 'src/devices/papercolor/artwork/rear-upper.png': '02415ce1ccbc54770aa0159a43423cd4737893d2d6e53c1defe8f3855e780cc8',
 'src/devices/papermono/artwork/nfc-reference-redraw.png': '84418b1f8df02c9503c0c0aeec68f27485619837e772882873e2fc1d89b820fe',
 'src/devices/papermono/artwork/rear.png': '0dca37738f5ef4cd826e61952079341c4aaf1faf0a231667eb3bcf4283626fcd',
 'src/devices/stackchan/artwork/bottom.png': '0deafe45a2d1b4d7ee704e91386bad17e388fec103cbb5db0294f3745fac0a29',
 'src/devices/stackchan/artwork/certification.png': 'a3ac70830eed4e5a018889519b67ee7d8c48b231de546c9b41fb38d6fc544635',
 'src/devices/stackchan/artwork/side.png': '1ddee7a66b1c6bbe9385013b49f07c3176914b23e2d52cbe3d5972b50e72cd17',
 'src/devices/stamplc/artwork/reference-redraw-front-inputs.png': 'cd3f434c529a9a262d2ff0cdc435d448b7cf0d6d60841b94d868d2f610deba88',
 'src/devices/stamplc/artwork/reference-redraw-front-main.png': 'b7d449329954fe2cbaa183b6dbe82e417320935737a283cc96ef1830b65f2ee5',
 'src/devices/stamplc/artwork/reference-redraw-front-note.png': 'a24dba1b2acb11288dd79751916cc0023ce5a650345ac52459b32bd4b11b6fdd',
 'src/devices/stamplc/artwork/reference-redraw-front-relays.png': '059aa92d37cfa7fcab365ff233966cd29e4b84789d2bad3746b5f1aff935ddb7',
 'src/devices/stickc-plus-se/artwork/rear.png': '4e35e91fd8366af4fc3d0ac2e217b252974743d804361f485f93cf96839d6d2b',
 'src/devices/stickc-plus/artwork/rear-reference-redraw.png': '41029bc91e6d508863223bc67884bf7b59cf833290b8bfc31a9d3192ccf334ad',
 'src/devices/stickc-plus2/artwork/rear-reference-redraw.png': 'eea414ebf0de2d0aa4abbb255c711cc42b4c109e1b01839a6b76ef6714cbc2de',
 'src/devices/stickc/artwork/rear-reference-redraw.png': '3061c0e1580edbd1060dfa2539651bc4ba2ebc2f9b4eeb8652c54d6e4ae99d7f',
 'src/devices/sticks3/artwork/rear.png': '3355803393cf98bc6d8c07f173173c1228bd69c81320ba166710e5dc78cd7fe9',
 'src/devices/sticks3/artwork/side.png': '672ea111bf918e6f4bfda888a0d863fd494c4f01be58f99008aca31579637194',
 'src/devices/stopwatch/artwork/rear.png': '6904bb6fca8b8d3ca153a439ade9b58ec0c065c35b7ca4abc072227590602b39',
 'src/devices/tab5/artwork/battery-bay.png': '1a7be15037a0c871cc9472e64b910fb189e7767d8685620ebbe63b36f3d32dd7',
 'src/devices/tab5/artwork/certification.png': '6159d5d031fcda48680279d9f3c8277ee80a90d45852247eecf0cbe4cc570bc1',
 'src/devices/tab5/artwork/gpio.png': '61fb3b827d97cbb4c1728e9340f090d4c3cc5acb56ed5853810bd154a5cc8bba',
 'src/devices/tab5/artwork/headset.png': 'a3d1a6f65a11a1794167018d54cb15baae25d22f47578fcfd6d657b579a86559',
 'src/devices/tab5/artwork/name.png': '52ab0b0a991bb6c2575d59c44bd2352373aa48731c348ebf21d754eb0b9f037f',
 'src/devices/tab5/artwork/port-a.png': '7c6d36e7cc17fc2957db62bf3320d9f0342d40f3fddec3dfd9e3ee75b9838f87',
 'src/devices/tab5/artwork/rear.png': 'c3907cb82c894cd5c9101736fa4ca070443713ee5597745d8eecbef8a8d57a5e',
 'src/devices/tab5/artwork/usb-a.png': 'a5d35fd52edb476111b4740e351a1224d1a7aafdd06304586265382d34f9e60e',
 'src/devices/tab5/artwork/usb-c.png': 'a11451303712b7e4684f64639d3949a9858c5542e84bffe2b76da0325417d50c',
 'src/units/2relay/official-back.png': 'd3f0b67ca06ec771f9046d7e5bff23dd0317381ad0079466b585152a6534cb19',
 'src/units/2relay/official-relay-1.png': '760cb483fa481347a39707f4d6c87fe315bfb5d3cf9453b08ac3ee46c8f4f646',
 'src/units/2relay/official-relay-2.png': 'a9f677916cb098e7bd4b487f6e531948a0072553796370d96d748a83a58a4a92',
 'src/units/4relay/reference-redraw-front.png': '86679c08c590d56d40a6f508350423347f18bc8a453f0dc039ed21528fc54b13',
 'src/units/4relay/reference-redraw-relay-1.png': '20b62b1b846d418f76cc746086c5e5507c7f73e0a906d7b30a0446d766774477',
 'src/units/4relay/reference-redraw-relay-2.png': 'cf33c8199277370bd9178390d8dc3fc6add8b6d499a78ea2a4d2e6c56af62fdd',
 'src/units/4relay/reference-redraw-relay-3.png': '7f6afd36fa05ecb8c4e8f8acbd46f2db34830c9c02d0e7003da635a0a7e01506',
 'src/units/4relay/reference-redraw-relay-4.png': 'cb736a2e8f608e094f9b7dff65ff1691360454d14a7805ea6fc3c21bb2ef2ef1',
 'src/units/8angle/official-back.png': '7d0c399615152ec995bfae07e16fb693b085fbb678898b818305b86887eff0fc',
 'src/units/8angle/reference-front.png': '92d885b5679149cf4dfb553374afba5ffda6d8439454e69e015338c23e0c921f',
 'src/units/8encoder/reference-redraw-back.png': '55e7f1af4b45064e518fc1c3765bb1494cbfdea155c13f79e0c6d7f4addff88e',
 'src/units/8encoder/reference-redraw-ch1.png': 'ff28595ff2f296d4f6139970c23c9fcd6127cf419a8914a5cd515aedc8c0cb38',
 'src/units/8encoder/reference-redraw-ch2.png': 'ba86b7fefae7cfdcb9661a58a5a556f78d45c5375c6108b83df23a603ec2875f',
 'src/units/8encoder/reference-redraw-ch3.png': 'e1b78c044a06018aa61eec26474594f479508826a57afd35f179b49216178c77',
 'src/units/8encoder/reference-redraw-ch4.png': '4607b8d0b8a4163603c09ea9dab123ea32bb11b934639723f5e30704575cd553',
 'src/units/8encoder/reference-redraw-ch5.png': '226ba271fcaeb2bca29c9004818285f1eedb11805cec37110edbb3f0ab1f1a07',
 'src/units/8encoder/reference-redraw-ch6.png': '9c7d4c3138d374811993b239f19efd4d85328ce915057028b39d99fe54fb86a7',
 'src/units/8encoder/reference-redraw-ch7.png': '127593bae227b37072f31679756eeed4e61da4fc4f4e1a774543fc24adfe8643',
 'src/units/8encoder/reference-redraw-ch8.png': 'a8737339527636521153fec14ccc47d552afc9333606594989e1c6453ceb7369',
 'src/units/8encoder/reference-redraw-sw.png': '61eae86097e2cd83a7013ca28edc0c62dfccf0786c50c0dcb2464b0f1cae065b',
 'src/units/8encoder/reference-redraw-switch-0.png': '9d3ccd53d7fef9f25a182f967bea38ebb1e0189805e3e0ca4d9ceaf36afb3d3d',
 'src/units/8encoder/reference-redraw-switch-1.png': 'deaf07076c1e4504856580556bec0623efa5b381b05b377f659cf07dccd1a16e',
 'src/units/8servos/reference-redraw-back.png': '9ed466fdc500c629aa3b1392e283588fa220685ead4342245826be58298242a9',
 'src/units/8servos/reference-redraw-front.png': 'd0aecf6ad446b828141c7f0d60ee5985af489fb5292f685ad07908aee9ce86d7',
 'src/units/8servos/reference-redraw-terminal.png': '610f5dbf1e1a6deabca89d7587bd25b605832b514cc4e3e66945ac91c199eac9',
 'src/units/8servos2-chain/artwork/back.png': '778ae5edf5998d74c9f4ef55fdc12e1d8537f13e6548396096ed4d187129b0be',
 'src/units/8servos2-chain/artwork/front.png': 'ab95b250fdee8b052ff70cdb7cca185c960bddedb6cde6605f60ec738d81d4c8',
 'src/units/8servos2-i2c/artwork/back.png': 'c3bbb3d20c137760b25c87922d2d7a45f81af536c2a318d1438456967bdb2a26',
 'src/units/8servos2-i2c/artwork/front.png': '17abc0d5069ceba58e3f66322cc357376bf292a3218fd572b866876a38f6a7b8',
 'src/units/8servos2-i2c/artwork/selector-scale.png': 'ed50d47b6b7f06bcf9dd1f6571f43dce4d7a271f5bf1ce750e25566b264b61f6',
 'src/units/ac-measure/source-vector-back.png': 'e81f1ccc7c0aca041d337863e50e80fd127e555787e18cffec0ae1ba41e03815',
 'src/units/ac-measure/source-vector-front.png': 'ec26295b907359185df0dfb65775b99796275469f7ff3c8bf199097fb1fcd765',
 'src/units/accel/reference-redraw-back.png': '372ce5b17abaf20b949b01fa0bb5f821aac0b485003ed2fe16914f7af9ce2b0b',
 'src/units/accel/reference-redraw-front.png': '2d6c7da1091427a71cabc588daacda9d88fbea3d0e37393bb600b6f04cd52de1',
 'src/units/acssr/reference-redraw-controller-back.png': 'd7aa89f3294b5cc204d48f242689d9da1828adf7958842666ca0b790bc018bff',
 'src/units/acssr/reference-redraw-ssr.png': '33abafdc87b5a15d0e32cfc973db0476e37d49887e9b980b5f2b28a9b32715a7',
 'src/units/adc-v11/reference-redraw-back.png': '2723caa04804b95c55460329468486ffcc65e90ace14acc0007a955fd737f7ac',
 'src/units/adc-v11/reference-redraw-front.png': 'dada1e5ae1ccb43881c2f5e44c8e59f535811a6cad8825f08445e99715afceaf',
 'src/units/adc/artwork/back.png': 'df1c239fc24c5899f2b97dc84c812685b874399763f146d095cf1ec506d05255',
 'src/units/adc/artwork/polarity.png': '7879fd406e4aa517cd58eea9fb28b2b140db91ab9b670ee5289528043a4e2a0c',
 'src/units/ain4-20ma/reference-redraw-back.png': '8dd983edba1f1231a0e5f3e0f1b81bc94a8b500560e9d38981f4a5e41fcdcf03',
 'src/units/ain4-20ma/reference-redraw-front.png': '9c657cd045321972157c9a7b210c535ec14ff48e78a4c14a314c22746fc4ce8e',
 'src/units/ameter/reference-redraw-back.png': 'c439116b32463ae4ba824d378279eb3618de2b234c411989d3a2338940b4581b',
 'src/units/ameter/reference-redraw-front.png': '40ecff6d0ac72cf1181d37684108a2a1ef12c0e18f21b8d0ba23155ab850d125',
 'src/units/angle/education-cn-back.png': '70d2d303f0f474a22cb344cc37854f6844b9e0d1a73986e31c43e54eac093756',
 'src/units/angle/reference-redraw-back.png': 'a9371ad7f137db5aad82a8de369d060c63e02f1528ee3c26133955eb5974dbde',
 'src/units/asr/reference-redraw-back.png': 'bc9aaa27a71f88d2093fa4acef6e8f3f94d75b083693aefdf895c3dc7863a330',
 'src/units/asr/reference-redraw-front.png': 'ddd1b4911cc50289df98529bb3b4e5f05cf75ec710e80b0019a0c33300f4fba7',
 'src/units/audioplayer/reference-back.png': 'e89b4698e56fc58947fa23c4b7eaf13c036509b3a7c6e05970f2471fb73e27ac',
 'src/units/audioplayer/reference-front.png': 'd43010d90f995b681d8e5a5517db8a6923eef59e209c4cd16ecb696e05fe4274',
 'src/units/bldc-driver/reference-redraw-back.png': 'db4482f68e1d85d4866f44e0442a9157ea104c04c75f0c96f44112415983b0fc',
 'src/units/bldc-driver/reference-redraw-front.png': '2d8b71ffad16d93553d2e1c0c7c071e06c7853853def448ff3798ae5aff4c5a5',
 'src/units/bmm350/artwork/axis.png': 'c1f93c2ca719b679042f128d878a09c9125ffbd8083a494a1f6dd3e7b088a93d',
 'src/units/bmm350/artwork/back.png': '35b13182fe8572504c186acc6a864a8c0f6f591d20aff82ed5855b5f1ff1d7d4',
 'src/units/bmm350/artwork/front.png': '0c8a50aed0d5b29ca5e5399d1b0ead4cf79786468a5f2d210a92aca8ad59ac2e',
 'src/units/bps/artwork/back.png': '053e9008e198ead9820d44c791e12235617ff15e50a6b3e423e65a6747522d3f',
 'src/units/bps/artwork/front.png': 'd974d7cff547fcc4d21f6961f201f81ee4c82ac820c3d54d56c6f5800233d755',
 'src/units/button/redrawn-back.png': '86cae8fd5bae5251dcab6cbffec9516b004bd05b0535892ffd639117fa15c823',
 'src/units/buzzer/redrawn-back.png': '567518ada3bb3d4cf2094561e6a87b3a747adb0ab6e792647e421e23ee2002c5',
 'src/units/bytebutton/reference-redraw-back.png': '1f145955a04d2ce2b093c912f4dc601cff9238e114268f09d7c0416a43ab81c3',
 'src/units/bytebutton/reference-redraw-front.png': '31571c68392cf67212f0e441eed37a34cfe696f28bf38e45899c8dcd3c344e32',
 'src/units/byteswitch/reference-redraw-back.png': 'a32db7aa99fb046320476f3ae83af2c7b16e0e9211d64c0e4fb151a899ecf7d0',
 'src/units/byteswitch/reference-redraw-front.png': '4cdf54817475d4a42cfdb21850bfe0fd6179943b190e64a901d88c0e757137c4',
 'src/units/c6l/reference-redraw-lora-band.png': '27ca24d52a2b39524500a4abce97b3275ae6feefd143a3c1dd876b7b202e49ae',
 'src/units/c6l/reference-redraw-wifi-band.png': '2857879270e477178c78773d49c6f7a2f01b0ebd1f2edd46108a593679250cdf',
 'src/units/c6l/source-amended-front.png': 'e92eb0dde87bbcc5a17a86df90345905f9975a05ae29db926b588b030123cfd1',
 'src/units/c6l/source-vector-back.png': '767956bca0de2cb9bdafea5313330a1eb59711985313b1fc473f7da717fdb7a6',
 'src/units/cams3-5mp/official-back.png': 'c2099c15d4c9defee7d1dac9578cb291d27ca95860bb1ae581aa230da0f560d3',
 'src/units/cams3-5mp/official-front.png': '2f4fe0be1206d603024f8b8b7b213a642093de9a369010e2f00dbad5770b7af8',
 'src/units/cams3-5mp/official-pinout.png': '6a1e9fcf21bbf816f1a31aaacaf93b4e80a60febe2bdc937ff33acb8b3979028',
 'src/units/cams3-5mp/official-top.png': '0a61992bf1d4e1e5620fb42b298d5bf1258597bad8bced95e88b09cc4be86086',
 'src/units/can/reference-redraw-back.png': '414aada2eadb011d6b9caa32161bb29b0d33c72a541e54575ab0231e3e8af7d4',
 'src/units/can/reference-redraw-front.png': 'baaa95ea6ea07355246ca5d1b51156fab82ce53b4942c1c9a6dacc31efedaaf8',
 'src/units/cardkb-original/artwork/front-pcb.png': 'ede4197555824229f0ebad996426caa58dbd4163f93cddf2a0e5ab73d1223c18',
 'src/units/cardkb/reference-redraw-front-legends.png': 'd5c8bfd33daba5f9168ef98677b18b9c310d5e56e538c6958729b6229d48c5a7',
 'src/units/cardkb2/artwork/back.png': 'f34c35567a9dcae5fcae361a0c687628992657c851871bd40f63e5d40558064c',
 'src/units/cardkb2/artwork/front.png': '2ccacfd4c5765a8c2e43f850ce3d9e7b404c4e9d909cc4f9510d7359e4ecd5fc',
 'src/units/cat1-cn/source-vector-back.png': '78dfba5212fa8e2eacbd7249a1f925e9d17048c0a34e1b47fa44c5d602b5a77d',
 'src/units/cat1-cn/source-vector-front.png': 'b2f7b9f8745ebe6c341fd6e7ac6c38eaafb85b872df15fb069b01ea9c0792fff',
 'src/units/catm-gnss/artwork/back.png': '493c83499f75474ff1cb6475835119f5d88ea66e425def12db7ec4ffc369bd6b',
 'src/units/catm-gnss/artwork/front.png': 'f79225e791af6a93bd6d93ea3df328b99cbd2b3c6e7e323927399bd7115e2d60',
 'src/units/catm-gnss/artwork/gnss.png': '0e30891eb144e4a48805c2971e581efa0d953d6930c7b56240dd5231dd8198a9',
 'src/units/catm/artwork/back.png': 'ae85572c8f228e459afc455c0197861e690f6c2395a74b2f654371ba51f7843a',
 'src/units/catm/artwork/front.png': '4bda3062fbab648d5074eea04e5120ead2f5b738c302ace2ab17a8b844859ba2',
 'src/units/chainbus/source-vector-back.png': 'c4135f27816e1f58d0234e160309c97964330a8766bd8803a4090eb60858b289',
 'src/units/chainbus/source-vector-front.png': '55fa2e31b37201fcea2ebe03de997952f0e2a87beab0534a3457fa40c071c546',
 'src/units/co2/reference-back.png': '57d3b7a0f42b6374b60f56b8c68639bf7e85bb4aeb39c95b76fa9ce0dd5ea451',
 'src/units/co2l/reference-redraw-back.png': '924c737e622b237b930b5639b39a6950f976ecb3fb19b0d1276118d65010a044',
 'src/units/co2l/reference-redraw-front.png': 'c014967d34d0301865164a312efdff80ef818d94250df26ac4d83189df988509',
 'src/units/color/reference-redraw-back.png': '2d7e3b02d5d64b7873488e42566fad6aa4b68a13db7c6e52f0a802dabf1b34bb',
 'src/units/dac/reference-redraw-back.png': '46f959d8a3928af68ad5e2e4d4ff0c5c2ba1cbf15e7c1d16cfd86d9d35401831',
 'src/units/dac/reference-redraw-polarity.png': '3d6543686aedb7dedda293bf80a9cdd65ffd82808dcf55d1014931e5e5a33396',
 'src/units/dac2/source-vector-back.png': '1f4511a6281c3e5fc79a1367d494de39980730fe57b0483aa0dc9a44bca769b3',
 'src/units/dac2/source-vector-front.png': '1d4160a0fe69f2552246366deb29e71ecfc004e40d029ae6128b8da18774b4e0',
 'src/units/dcssr/reference-redraw-controller-back.png': 'a29480edd372d7aafa9f04429d7b0f6f0ff1bfb6e2bde6958a5b3dd8e6bb87fc',
 'src/units/dcssr/reference-redraw-ssr.png': 'fa0d16b028df121517767b41d2adac4001c7d499148a5f61b236bf8450421432',
 'src/units/dds/reference-redraw-back.png': 'ac6f48679f58bae7c27aa25e8961fa65ab0def16a7f02df705901b4a5e71e33e',
 'src/units/dds/reference-redraw-front.png': '2c2b04c1effff55e30e53bad0de2a092bc5af16226c0d42b32c84e48ccc0dabc',
 'src/units/dlight/reference-redraw-back.png': 'e8fe607350a122b91bc972216f1e2b155e4d54429a00dd6cfe32d21efab010d6',
 'src/units/dmx/reference-redraw-back.png': '29bbf65d859dedbed0af7dc0638696912b6d7f8d480a56f3e0b81013b4c78179',
 'src/units/dmx/reference-redraw-front.png': 'fa182113ed222085ba19e2dc020cc16ef155f0cc2e89142dd070c0ab466b62fc',
 'src/units/dof10/source-vector-axis.png': '1386dc6fbaff4d3bded9bc0b4cf931f7476e026b211c34467a420b6614bcdce7',
 'src/units/dof10/source-vector-back.png': 'e74c0ca5d50a1d037428c5a5bcd511c57ac168de3636f8a58e2ce9a3451d942b',
 'src/units/dof10/source-vector-front.png': '9bf0cbf363c61dc66450005378afe6766eb24b161688629ce386cd73d9ccdc34',
 'src/units/dof6/artwork/axis.png': 'b77647ed7deac03ae58714e5ef210cdb7e951260c7fadf012d8bd27b79f487cf',
 'src/units/dof6/artwork/back.png': 'ede90338928b000523436ad40d019726a69b11a4c3d7fd05550ac62f34969acd',
 'src/units/dof6/artwork/front.png': '5ced84ba6414986c18ff7f4c229abb9fef6e7dd3cdc5af40b51933efe6d820dd',
 'src/units/dof9/source-vector-axis.png': '068c569b2820992fed535966334006a94a7348b44bcee7a5a12b639f3c6db264',
 'src/units/dof9/source-vector-back.png': '57a098b59bf0aacfe740d5c805ad31b386e83a706406c45a94bbaf933bfd663c',
 'src/units/dof9/source-vector-front.png': '8a60f413333e006f355e378e7683573fd4df32e937641424abad3aeef2103adb',
 'src/units/dual-button/official-back.png': '07efcda08c3cb06b69f84b56ea2ca6a4a4573bc0e75f458efef0ea00a764dadb',
 'src/units/earth/education-cn-back.png': '8233710041a4e755b23f6b94aba2c8da3cbb20c565c9982de6a6b87a948ad02e',
 'src/units/earth/source-vector-back.png': '9d0173efc4a515981e521f7537612352a0f6e310e5475b0e4cb657b477d5b725',
 'src/units/encoder/redrawn-back.png': '84ef1efc55b7545431886827816324caea75a63e059691ffc1f9ee590d8faa61',
 'src/units/env-ii/artwork/rear.png': '92c5c39ed3aac3c7f3c2c718d12820ed33e8e408d05f88a9d39166ff2597aac5',
 'src/units/env-iii/education-cn-back.png': '4280ee9b608a15c256f43a44f8a7b840a121578be8453bbee904d6555a0e9e3e',
 'src/units/env-iii/reference-redraw-back.png': 'f367f87a959b0370a191919f55d8cad9b331269e51bfd42f8710f9a9891b1f22',
 'src/units/env-iv/artwork/back.png': '27ffb2b26ab284155b85495d26f4a7dfe028e51ee55764438382f285c3d077f6',
 'src/units/env-pro/official-back.png': '2d0ab427ea9798cb4c575ef64f12262cc4997ef9dde5be8dda32766fb04bca79',
 'src/units/env/artwork/back.png': '977bdd2afef4561e253d20e4696b74fdcc918328e4c6bdb8895d96fde6f8dd85',
 'src/units/env/artwork/qc.png': '27dd05c7f1c5fefd1e29e9efbbd03f40b3cac087299f5ca0b5ccdc84a5e1323d',
 'src/units/extencoder/reference-redraw-back.png': 'fc99abfe3b64bc32e9e8f44bed11dbb9124d40b18fa7e59094d38bbb24bd72e2',
 'src/units/extencoder/reference-redraw-front.png': 'c6cf2986da7c2896564ea916f7ddb98d1b455726a3d229177e22fa152e9a77be',
 'src/units/extio/artwork/rear.png': '6645e73fbaf835e24a69ab9e4b6f56fd6dab7fb879653bc1cd419103dc62f200',
 'src/units/extio2/reference-redraw-back.png': '5e8f50a6f6bbd15848e554508240b8fde198e05a66c206e941a7b9c653e93372',
 'src/units/fader/reference-redraw-back.png': '5b2a4796113e29ad2962fa8bfb22ec3b165fa68245c7e3f11ff480feb7ba9d86',
 'src/units/fan/education-cn-back.png': 'e4a51df5d1781e8bb8f4df08a736ba7339a2aee45bd7268dfa2d9a0fdde80712',
 'src/units/fan/reference-redraw-back.png': '8d0fbe6e19dfcce95b0690c61b2c89db03e6b8841fba89867e08e14d2b311d20',
 'src/units/finger/reference-redraw-back.png': '565f0f8cfe38539733df372a52b6648f52da7fa1ca8b80f34b7e98af84807834',
 'src/units/fingerprint2/official-back-vector.png': '05a2b85bb1f906f358ead5004531fda274d2adcb8ff430c64a04b56ef9206a6a',
 'src/units/fingerprint2/official-fingerprint-native.png': 'e5bda8d76c7e54f1f9ea8b316a5b143f379123fec22355cd91dde16e0d4b2302',
 'src/units/flashlight/reference-redraw-back.png': 'bd84d2a8f48cb0244dd55df945f71cb890950242dc677d83ca654a02058199d2',
 'src/units/flashlight/reference-redraw-pcb.png': '1f0cc8b1d61ea2e28f4b72cb799c09ec3c1df21b38fcb9e8938c0f1a3b790d9e',
 'src/units/gateway-h2/reference-redraw-back.png': '8fdec63aeb34ee0602b9e15859a74a34785d8837df92c47de716bfc2d9cf0fcc',
 'src/units/gateway-h2/reference-redraw-front.png': '422d1d38572ed904207df2823c2edcebc8a3bda8adc83f3b3fd05de3837b6a9a',
 'src/units/gesture/reference-back.png': 'be933d4274625abf9adaed93953ee189c4887e25983e40f1497819fc01ee5d0f',
 'src/units/glass/artwork/back.png': '0e86b235536ea1670edd6eae8532832983f8ddec48b0a2fefb43414bc239d75b',
 'src/units/glass/artwork/front.png': '2a311fdc1f5dda36f64012c0b90ff60725c456391897044b792990ffc13c1065',
 'src/units/glass2/reference-redraw-back.png': 'e955f7ab7f75eb315d5e8689f79a9df3d58c408ce37dabb621c258aee62925f9',
 'src/units/glass2/reference-redraw-front.png': '06433687000369c421f564342cd59591fea7fbe6f0258a44bb679c001d835e79',
 'src/units/gps-sma/reference-redraw-antenna.png': '719a1170a38c517cc98fc50699c57698c2d891c1763aaad0449a1841e66e48e5',
 'src/units/gps-sma/reference-redraw-back.png': 'd85895567b329b44889335d67593f8033cea4c269fb03f6780094c29be2ce779',
 'src/units/gps-sma/reference-redraw-front.png': 'f278c41bf9bed1adeb5b49c2d0a15728e6ccdacbcc29b8bfc0acc1d305da2c44',
 'src/units/gps-v11/reference-redraw-back.png': '1de94b71d41afa09cb04928663971614bf54ce3a2f9f1d5502a47188c2229742',
 'src/units/gps-v11/reference-redraw-front.png': '1b7977ac30c016c313164488fc9d907b95c4385167e5cf9331e6cc4d9e8bfb3e',
 'src/units/gps/artwork/back.png': '8984d122965bd5a18709f70022e07a07f02bc173cdde73352af74647c32998e6',
 'src/units/gps/artwork/front.png': '8c5d9869a22ade9a5092791c11805f2c41839a5f95c84f7ad88526eb9f0e48dd',
 'src/units/grove-to-grove/reference-redraw-back.png': '5f942e9a01db13afbb50a69fb589d2d8d5c2b0a7e169647099cd1c5699560742',
 'src/units/grove-to-grove/reference-redraw-front.png': 'cdc695573a985ba7e37fc51b2079729579d501d762aa82503fe9cf80b932bb3c',
 'src/units/hall/reference-redraw-back.png': '5b07c4bff51023731ac9fdae64e0db5ba46b06858f1261e34c6275ee3f856c7d',
 'src/units/hall/reference-redraw-front.png': '65afd822b525f79ef83fd7ef20a61e88829fdce3c3480f8e9d5f05e3d27458a4',
 'src/units/hbridge-v11/reference-redraw-back.png': '6b8df63f1b8dba1264c1252cd42a1464004d5260b0804f98626f5a85a41abd83',
 'src/units/hbridge-v11/reference-redraw-front.png': '3b4a974c20cd7691e23aaec5153ac84c8a466972b53183c073720156b0f16077',
 'src/units/hbridge/reference-redraw-back.png': 'd8bbf821ed5501eef3d770153786f20109b773214209dc4c106ebb199b3be87c',
 'src/units/hbridge/reference-redraw-front.png': '77d492b23d620cbcc377a606b255f63740631cc6ae9fb16f3d1164f4c43f7c78',
 'src/units/heart/reference-redraw-back.png': '21f72c5254beda58796eb24c665e80d8baacd244d178f8ce621561c247fa04a5',
 'src/units/hex/artwork/rear.png': '341abe326e6e7281c2b4d5708b94fa17ed367507c94faad1d4d35fc84696c938',
 'src/units/hub/official-back.png': '56243d519e2fc690b9b0cd5f55c57a5e942f8642114fd1bb8d4a1aede18bf0ce',
 'src/units/ina226-10a/source-vector-back.png': 'eb789c7ac8ca49d3139f09617e3fc82a7700574bc4379f64ab8f83c94150b992',
 'src/units/ina226-10a/source-vector-front.png': '103784518f71cdecc8b9aa59b289d4a76c87d31ec17103ce8af8ba74e973c455',
 'src/units/ina226-1a/source-vector-back.png': '3a0f28b2a755804b98ad2d7c149bb2325c168e6a4a03c3027d05a17386fe6d3b',
 'src/units/ina226-1a/source-vector-front.png': 'bbeee09b32f54fd3b07f61cc73cf4b4eea22c28ca245efbe7efbcd40979b6c91',
 'src/units/ir/official-back.png': 'da1d2f124e020e74b29a624a4045a53c9cfff9311a4c59c3746e4b3a4a841017',
 'src/units/joystick-v11/reference-redraw-back.png': '5e6014a7210528c412b7038c0f8d7306a855daae9a15e7cf15de8b2dc300c36f',
 'src/units/joystick/reference-redraw-back.png': '700b2df3aaf2fef33283606124845354990b7619f498cc90ecc0830cac1951a7',
 'src/units/joystick2/reference-redraw-back.png': '8793a06b65467b92080fe3f9e0571e70ced3e64128f5ce24df8c98fcc53ce0a5',
 'src/units/key/reference-redraw-back.png': 'a021dbba89b63b957c147b29870024688aa3cb20af7ba181e259647c0dd47ab7',
 'src/units/kmeter-iso-v11/official-back.png': 'c08456abed1f7206a1a0f9c3b92336cc2f5bceac6e44429ad50436e06479e426',
 'src/units/kmeter-iso-v11/official-front.png': 'f85a9e5f7952af2b59d84872ab2cf571f914df83b7997fae4e638877da5d7dfa',
 'src/units/kmeter-iso-v11/reference-redraw-connector.png': '6595fc4064534856d9228c0b314d90b59404e38caf253a41e2ef6d7e4482c0da',
 'src/units/laser-rx/reference-redraw-back.png': '6e3aa0c144abdb14270a9b73dbd13a8632f28a0a99e0d74f44cb59e5bf45e248',
 'src/units/laser-rx/reference-redraw-front.png': '7b133c1bbf31cfe26db9a9bd1fd2af55ac0a70cc4b3dd4bf2445666bd8f0b869',
 'src/units/laser-tx/reference-redraw-back.png': 'f1cba8f1019cc2a818c649c8a42b6675652b6c0d80251c4fc1b7faf233c8fc3e',
 'src/units/laser-tx/reference-redraw-front.png': 'f387fb617a9b73d695f27583ac8cf084aab2ba581a10d7e8b7fd8bf43488454f',
 'src/units/lcd/reference-back.png': 'c3b6da96e2257fa0e05e4e0aee470e6a2c4be6f166663a51eb31991b3fdc2142',
 'src/units/light/education-cn-back.png': '5f8047883cb05d59c8577bd11edc91b0a70d88066b5335931c8d1bc2b49c824b',
 'src/units/light/reference-redraw-back.png': '6f82495340f0e8250135060b40dca2b0419487de03da4d3d8840091c854ab3bf',
 'src/units/limit/redrawn-back.png': '6d79328da035f89247f6c3c229ae9339452df7950dd8172fc08f3a3d768c56d3',
 'src/units/lora-e220-433/reference-redraw-back.png': '25c318996af0fa5a6a38929a4849e987227684fd8ca31f84cc2777bea00f9f6c',
 'src/units/lora-e220-433/reference-redraw-dip.png': '7e78807987e0405ac4536ff253a89314c1f267abf0e5eb0ffff811f09531754f',
 'src/units/lora-e220-433/reference-redraw-front.png': 'c783d1958dcdbf64b02c61fe97c8224a958642f6ecbf2b61ed02968bb95b7809',
 'src/units/lora-e220-920/reference-redraw-back.png': '7846463cda47dea3da3b1b9c6a0c855f04ed30e351e1e6f69719f2c4f9383d0b',
 'src/units/lora-e220-920/reference-redraw-dip.png': 'ace45bf3f061d74b15133de9a93fd18688902bf346faf8d3d185f0cf0da4a341',
 'src/units/lora-e220-920/reference-redraw-front.png': 'b98beca79fa196f993e09bf37b0303529f0f5cba8db4155519ada00b4a990c66',
 'src/units/lorawan-as923/artwork/back.png': '1bfb0ad97e59ebfcb2ed4463f12884c0a44ec1e9e5ebf9d20e4faa8540235358',
 'src/units/lorawan-as923/artwork/front.png': 'f51e1f0d59812bc3099f921541ecb9464e849990c05bd57de8d52b920cd00339',
 'src/units/lorawan-cn470/reference-redraw-back.png': '893b9686f8a5d76c364fe5681af03e07016a97ad1fec86e96751646673a0578a',
 'src/units/lorawan-cn470/reference-redraw-front.png': '3c4c2427b8a04328900acb77e2a8a7821af4e711d45a9021e00367f4022c972f',
 'src/units/lorawan-eu868/artwork/back.png': 'f7b2da09ec61b49dadd4f7bd79bf2864c0fff713b89b7f54e29ceb303cda99ea',
 'src/units/lorawan-eu868/artwork/front.png': '9eafda1ec3846ea53bb9019e61344096bedbd4740f05072e9fcf742f15263768',
 'src/units/lorawan-us915/artwork/back.png': '6c033f0506147acb0dbc129b4677a21fe57c0bdaa55d24c186246116ae1996ee',
 'src/units/lorawan-us915/artwork/front.png': '096195de6f17515b0b55f98d80d935dc4ba2d2f3e8bd0fecd13b64814ddc05c1',
 'src/units/m5-bit/reference-redraw-back.png': '4e1718846a0a3de4f6b3dba2f9fa0c29025df1f6a2c41d6feffe06ec3cee50fe',
 'src/units/m5-bit/reference-redraw-front.png': 'c7518fcf76156286e04506e206b424243b0bcd1dcac972c304a695beb5ced188',
 'src/units/m5camera/reference-redraw-back.png': '2a1098ef845d4a97c1928c826018f8bb4b7be661b40eca336a63339d6bb6491c',
 'src/units/mic/reference-redraw-back.png': '439b5ac88998f36e15be873dab780ee40aee9105325df16c38fd842c508d582f',
 'src/units/midi/reference-redraw-back.png': 'dcf65077e69daf77c5478dfeb3b1a0863b8631d40dd0a48a73da8acb4c35293d',
 'src/units/midi/reference-redraw-front.png': '43cc24f2aeabef54a67cd1f819f4396b4494a3f608cc85786d0b4a3488feb196',
 'src/units/mini-bps-v11/reference-redraw-back.png': 'bf490a396cac2cbe632f5019c2620d41f612ffcbed76add74f5833105560d3eb',
 'src/units/mini-bps-v11/reference-redraw-front.png': 'aded45a708b82af9ba8e44d9c69bdc9323769f92ccbc14aaee313ac7d1443cad',
 'src/units/mini-can/reference-redraw-back.png': '89e4868a89940dde6cd88a111464345f7e96acedd783723fe71271733f4b8b2c',
 'src/units/mini-can/reference-redraw-front.png': '1714b76519114035954d76b197814f0a148e6120750e20232cc354b4f42250b8',
 'src/units/mini-imu-pro/artwork/axis.png': 'c97e95f4a6f7db64dd2910f95c1502d82acf279709e5a858b3e54c77387fcbab',
 'src/units/mini-imu-pro/artwork/back.png': 'f29910c1d40c46af190e8b5b9a7bcfb9d98dcf85dae85560c1ae077833029c98',
 'src/units/mini-imu-pro/artwork/front.png': 'aa57e9074bc35b8727c302d79160aacb41c988b003b04f1d57a9145256f78a4a',
 'src/units/mini-imu/reference-redraw-axes.png': '782b63744f03fc0c4ee586032d63bd24f2c89be970cce4b480a4548fed40b727',
 'src/units/mini-imu/reference-redraw-back.png': '20fcb984f0241bdcae2c0ec38a5c071279c1c28c819d8c210fe7d58f19f8a701',
 'src/units/mini-imu/reference-redraw-front.png': '0358b4be273734133513c12211374a03f804aebdff56662834f13d1ae291b23a',
 'src/units/mini-oled/artwork/back.png': '3e4e40055763892d67dfdaa7b9624d5e82c9d03f14d9d7b188ba01a33a6d08ae',
 'src/units/mini-oled/artwork/front.png': '814e6882a758116b51f82b1a3e075d4c7213cc78e59eb90af2e580d3bdd025c0',
 'src/units/mini-pdm/reference-redraw-back.png': 'bd4dd60db64f757fbb4743e8ec14c79eacc9359e422e47b552f9506b4159fdd3',
 'src/units/mini-pdm/reference-redraw-front.png': 'c3e7fd8c65480b65f22efed5f63fdb4575c5c015ec3d3f9493c1ffa81b23a22b',
 'src/units/mini-proto/artwork/back.png': '0164e7bb7ec9a4e2a128285f057076a92b662478f34a20e5ee63f59e27709e2d',
 'src/units/mini-scales/reference-redraw-back.png': 'c038a4338951842b43d278186481753d1c2500f87338d10e735d5868d3469315',
 'src/units/mini-scales/reference-redraw-end.png': 'a5c869e1d194770c097fc93c1398769f8a51c2c6987b4db18584add814416c37',
 'src/units/mini-scales/reference-redraw-front.png': '8256d1b3ffd950d58d3262689044c379ed4c3190ff8e8b538fdf2f5146ff471e',
 'src/units/mini-tof-90/reference-redraw-back.png': '6465a0039e9dbab22c1de18e8ca8d22276b6b1786d0a6f0ce8ddbb7c3eb9a01e',
 'src/units/mini-tof-90/reference-redraw-front.png': '9c52025f331eded0f49c1f26828ed55290615243179fd62377ef603049720a60',
 'src/units/mq/reference-redraw-blank.png': '7fb64be6c55cf35ccdf6ed47e4bf97018c15f5242b79669fc9ccf180aff62fd4',
 'src/units/mq/reference-redraw-mq5.png': '0567220bcddff88a5ee06324565e1695bce07497839d55cd043cb738b44a44d3',
 'src/units/mq/reference-redraw-title.png': 'e88ec9c3aec57dda723b04ea81a6d182229d0389a64b620361de2017d77bfdab',
 'src/units/mq/source-vector-back.png': 'e966af82aa43f7e2744140803b62447c762c141a7acd299148383bb7e6540776',
 'src/units/nbiot-cn/artwork/back.png': 'cae96908e4d38cf9b32c09b31eee1548e3bfb760b04ccf17121b2d51565d4d25',
 'src/units/nbiot-cn/artwork/front.png': 'ccff981b4907a20a5557394905d6de232dcc04b518422d00a06a6be9e35943ce',
 'src/units/nbiot2/reference-redraw-back.png': 'f748e5795ee925b9625b897f57caf4226ee24120a84ae0738b21d86b4b89214f',
 'src/units/nbiot2/reference-redraw-front.png': 'b86445242f81a67413eb82788ff057dfd29bf2af11518ee9da0a78a7b2490c8a',
 'src/units/ncir/reference-redraw-back.png': 'd3d1721c9e0282b2eadca16ae751c6307bbb353148322807e8885e8e30fcc76a',
 'src/units/ncir2/reference-redraw-back.png': '2054e5e354d917d3908788602dca60e4413386ea8869c678eda99abf228039fe',
 'src/units/ncir2/reference-redraw-front.png': 'e417403e9a726b901a63ddaf8efbbae047adf62e965f74fbc61beaf66f6c9137',
 'src/units/neco/artwork/back.png': '490e5ad82f33cb71efbfa501bd694f432bf7cf645c5bfb1d4c7e3fcc7dfb88dc',
 'src/units/neco/artwork/front.png': '1d1137af78f54cd72f6e5d2900d9c90953092a554d464cecd98d8356478a6852',
 'src/units/neohex/artwork/back.png': '187fd2d8183416338557d57ac01f88aaea926b808058d6dd68894a66192a04ea',
 'src/units/neohex/artwork/front.png': 'af95a87510acb7bec81522916082acba073f7eb7ddb51e0384b3dc15779cb696',
 'src/units/nfc/source-vector-back.png': 'c25adfa93762e9acd2f771f16437e0909c16ea39b90b5e93a0c9ba2bda796d1e',
 'src/units/nfc/source-vector-front.png': '0c9feb4d338d1c4109e154216a7fe3e7b447960527b5ca986e2cdf152e931192',
 'src/units/oled/reference-back.png': 'cfd852f872b263bf64fe8b379cf718cf1a51e769076ce7baf749d69f145566da',
 'src/units/op180/reference-redraw-back.png': 'd13f03033cbdea6b3cfb1dff2cc62b0f790bc7292daa1b396651ba9842f4c045',
 'src/units/op90/reference-redraw-back.png': 'adc1f1dccaa4df4363ec8a8b22e8cd45f84d02e3db7d21ca88f7191d02f1957d',
 'src/units/pahub-v20/artwork/back.png': '3341baec127667e37418d4c7c7f9a0db5a58153b35406422ef8fe5670f36dd7d',
 'src/units/pahub-v20/artwork/pcb.png': 'b4580c50ba34a58611b28e9260e9632b0bdc358ab479de2050b3de85cef59d0f',
 'src/units/pahub-v21/official-back.png': '6c601a2c540e4bdf6318558b09a660ff6d52d1a1a573b53501cd180664902e2c',
 'src/units/pahub-v21/official-chip.png': 'f371a894269e53792c6ce7af4cbb774fff305cfb719ca2f02c0a7ef120337ab6',
 'src/units/pbhub-v11/official-back.png': '5fcec5d5c36da7e49aa3ad047c2d037a4fa6768eba30025f5614443fc4a0f954',
 'src/units/pbhub/artwork/pcb.png': '1b8ae244a12dca5417b222b4b27eb8d3f399827b28d30c96244ba4aa59e99675',
 'src/units/pbhub/artwork/rear.png': '51c90d56cfac7971e07af11c4a53ef85249897a6ab6774037db6fce85047f2fb',
 'src/units/pir/education-cn-back.png': '734922c95c3c39b067da0d5a2e6016879da1d3595af5f319033457389fb55e5e',
 'src/units/pir/reference-redraw-back.png': 'e4d0ff2c3b16b369331bd3a68dcd8ad10540ec71eb660a7e325b5bf6ce40a34e',
 'src/units/poe-cam-w-v11/artwork/front.png': '04d782421e39e865309749abb411d868895ce13233b7edb9ee9ed8208841d574',
 'src/units/poe-cam-w-v11/artwork/rear.png': '8c53ec563aed0a1093572fb4908c1a7ab87c3bfe7e7c93e1190332ab929f7719',
 'src/units/poe-cam-w/reference-redraw-back.png': '48a793ab0b8b8095827459fb103a7e654e2680f1561579b6d40867678dec4e82',
 'src/units/poe-p4/source-vector-back.png': '0103b0184670fca03aae709381b44d43a7b3e8cf83ce3fc29ea7c6751562ca2c',
 'src/units/poe-p4/source-vector-front.png': '643fbc5e0a51f83d171ed3c2b073db070ee91e953920f423681be3376e39cb4a',
 'src/units/poe-p4/source-vector-hat.png': '0ba7513b83376e5eb09235179559e8e80690fe69d85babba9d05ca9d4507cbf2',
 'src/units/poe-p4/source-vector-side.png': 'f27e8d5865401d32d0d561352668d4f1e37d4490b5c893fbdace187132e624d2',
 'src/units/poesp32/official-back.png': '619fb3e47c7f5a82b65b1099d288c8b6f9ed4ecde5aab33fee49787631cf604d',
 'src/units/poesp32/official-certification.png': 'd49fbdb663547d0cc811ece7396c5801151b1c97c912b12dc9201c1ed5fa0dda',
 'src/units/poesp32/official-front.png': '45785b1dc95c147379ca89bfe00c36cdca0b3672cbbb582d18899c2c8703c80c',
 'src/units/proto/reference-redraw-back.png': '9e3f02d6094db95ea7c697e0dacbc3429c8c8295338efa81d22060e55bc943cf',
 'src/units/puzzle/reference-redraw-back.png': 'f8c459d39256cd41f30e59deab0a9db4b5c71871a34869b8c5593e6821432c88',
 'src/units/puzzle/reference-redraw-bridge.png': 'b804389ea583592d3468c12d6549b674bedc0deb9311dad3d239fcf7fffbb1d6',
 'src/units/qrcode/official-back.png': '9a75f91bf05cf79e571c851a75c368b340711aed5fa8c89ab940e9fa97f11b8c',
 'src/units/qrcode/official-front.png': 'd1518e96ff3c414aab23a772fc6cefcaf48cb876937537f2dbd050ecd3e98eba',
 'src/units/qrcode/official-mode.png': 'df86d9c44149d52dd6960f54c50972227ee00110fa7092e2d9c2bdc2b288dfd8',
 'src/units/rca/reference-redraw-back.png': 'ada3b554f965eacd075c1a7f3d18c433c21a3dddc930c215239320a1acb440fe',
 'src/units/rca/reference-redraw-pcb.png': '9185b1c2d2381d2a8004021cc5dee79b08172276830dc8baad330ba6a9a6b5d2',
 'src/units/reflective-ir/reference-redraw-back.png': '96dd782986249ec4ffc86d17c026bcd315653a6a7a8838fee7dc44d0900179eb',
 'src/units/reflective-ir/reference-redraw-front.png': '587be15c51e9ead3eddef5b15d8c866dadbed5a2006268626fb8ecbaf583aece',
 'src/units/relay/reference-redraw-back.png': 'f539dd65481f57034cae9365b08e32c5c2069db6f1f206c7357be911233de721',
 'src/units/rf433r/reference-redraw-back.png': 'f83ca4a5d544ea2b230a8dfc9e8af4d6557a649a910ada315826d4d676a9da7d',
 'src/units/rf433r/reference-redraw-front.png': 'b92e0ba60edcfb53ab298b665e7b56305108a5c94c4ef6c4efde37d3928abba4',
 'src/units/rf433t/reference-redraw-back.png': 'ee26df00ff6bac58e24c4d5790d1086cbdb0ccd0c4d5adbe22b93e83b8142e11',
 'src/units/rf433t/reference-redraw-front.png': 'a6a3e70495d773c5d317b9d7380cf1063d9242740c254b92812de38fd6e41a30',
 'src/units/rfid/artwork/front.png': 'f27e41868ddce0036feccd50b15d9a29af1d0e44c91df0080795ac07661cda6c',
 'src/units/rfid/artwork/rear.png': 'dc5e2b611a4941c29c7f6367bf597f23df4855b1b8b704122e05b37e53342647',
 'src/units/rfid2/official-back.png': '33c7e0d72c5fa71590a50c5c67b0cf60caf51b10a5d61adf7806b36d20c26959',
 'src/units/rfid2/official-front.png': '898330c070a6d71c99b6fae3f9ce91f26f77320b2ac6d517d8bf477a72f0b662',
 'src/units/rgb-led-10cm/reference-redraw-input.png': '73159e3f570eb770f46e3cf5bbef245f226a21aeb3fcec7dd301c9ad7578903b',
 'src/units/rgb-led-10cm/reference-redraw-next.png': 'a59964f6c2fce1e2d6db6031d4f4fbf141fc04dcde73010584e7561792e2afd8',
 'src/units/rgb-led-10cm/reference-redraw-strip.png': '91fcc8bb35c7ff91f9616f4e80d2d77121fc0d614e874d66fcb88a125b500492',
 'src/units/rgb-led-strip-50cm/artwork/plus5v.png': '86def3685a178e1665e33082dc20dc482d7159949acdfa07529534e4dbc82b83',
 'src/units/rgb/official-back.png': 'f5f4d5e7f0924881b82764e6d44e40df0e594a6b2b4f96a46df7c8e9a83f538c',
 'src/units/roller485-lite/reference-redraw-debug.png': 'fc33203e371c0d60b00320aedd13fab497a349dfc90e76ec95b8d7793044ea2d',
 'src/units/roller485-lite/reference-redraw-port-a.png': '9087ece0bc43592d85288df0228857cbaa0ef8a5ec5983a767e91fd6fbb11a82',
 'src/units/roller485-lite/reference-redraw-pwr485.png': '0df2dbcf6a04685847a4044677509d3e8f038eb6efb3c60b0c887f1f1ad9da10',
 'src/units/roller485/reference-redraw-port-a.png': '9b8889f1b9757dfbc2fab2c08b549f7cc02758498a952641510a106bc4e27dc4',
 'src/units/roller485/reference-redraw-pwr485.png': '66e7fde9d29e43f3eefd0a992f89141e968bc4450eec80890713fb4315a87d1e',
 'src/units/rollercan-lite/reference-redraw-debug.png': '5e9c224b964ca1584f760965f56f3e37e184e7a71cb55c487726b35a7c21b59d',
 'src/units/rollercan-lite/reference-redraw-port-a.png': '765376d01c6e7b278035b8d3e7a548c49410d7bc50616e7d0007a36ac3bfd971',
 'src/units/rollercan-lite/reference-redraw-pwrcan.png': 'd40ce77e093cb74bebbfe0366ce7d346e38aab74cda0bd146471dede99001bab',
 'src/units/rollercan/reference-redraw-debug.png': '5e9c224b964ca1584f760965f56f3e37e184e7a71cb55c487726b35a7c21b59d',
 'src/units/rollercan/reference-redraw-port-a.png': '765376d01c6e7b278035b8d3e7a548c49410d7bc50616e7d0007a36ac3bfd971',
 'src/units/rollercan/reference-redraw-pwrcan.png': 'd40ce77e093cb74bebbfe0366ce7d346e38aab74cda0bd146471dede99001bab',
 'src/units/rs485-iso/reference-redraw-back.png': '4f5636ec582d8b08bc96fa47579d282f394df47272239fb0b1f080e5daa7e2c6',
 'src/units/rs485-iso/reference-redraw-front.png': '0852e4efa68ec93cc4151b675b385b8345023652c6de6f7183de046bb5ffea95',
 'src/units/rs485/reference-redraw-back.png': 'f32e4269c85eb180f4204126043515e2f01f5437f7eebda491fbfda0bf742ff4',
 'src/units/rtc/reference-back.png': 'ec8d087e5b569d0279914a5bb1aeb64470b1faa4e94e64fae77df8275bc2c873',
 'src/units/rtc/reference-front.png': '578e2a076ebac051669d0b980dd7df207aec92b4e0894c00b537f6fda976aeeb',
 'src/units/scales/reference-redraw-back.png': '79296445da43c71b2659a2af26f5c92decff5c31d087ea06b505281ed32e1c0b',
 'src/units/scroll/education-cn-back.png': '9662ad9d9f949649dcdc49eb8124adb482d026c122d2c14d9430a83dc52b4598',
 'src/units/scroll/reference-redraw-back.png': 'f0e4c29b17507f06f8a3725f9640a4a35dedeee174271e05bc48fa42fcb4ff33',
 'src/units/ssr/source-vector-back.png': 'b450cd59d9ef97b56aa1850f68da700923e046953e8195556022f71227cbeb1c',
 'src/units/ssr/source-vector-front.png': '2f1373ccd2446f68951494b12d700d7c06262ac5985c0e4818b304754a81c64f',
 'src/units/step16/reference-redraw-back.png': 'da553d39593acfff18d14b1b785503e8705d0043df1687c0a48e4031865a126b',
 'src/units/synth/reference-redraw-back.png': '25a5320710a04d4637ac5fdba9ec9957a37648be1baa31a6e081ae6d8f8a58f3',
 'src/units/synth/reference-redraw-front.png': '365d345d3d991df2612fd4f311dcf2a4e7116db0ebe998168b0a48cc9fef6533',
 'src/units/thermal/education-cn-back.png': '9f1e14950bd95fa15371c0f0f54ba4fc1c5b816d191d41430f178d7b78b59d35',
 'src/units/thermal/reference-redraw-back.png': '62a70cd62a1f2d33db877603ff6a5bfa77edfc1eceac2697d419100dae3f2e47',
 'src/units/thermal2/reference-redraw-back.png': '416519019c82e838d8fef427a093435ae335201391dff285de2878659b09b8b8',
 'src/units/thermal2/reference-redraw-front.png': '397991f5c79dda53f8bf5966bf9a6770d31663267ca2ffc49aca352cc3ddd183',
 'src/units/timercamera-f/artwork/back.png': '8518631db80ed3a9f4474f15ae5cc7ffd7058ecaf14062687b0d826abd88e12e',
 'src/units/timercamera-x/artwork/back.png': '34c199671e9a0a8958332ffe9248fc05a25e10b773b98a6e8f90e1ed4b9037d8',
 'src/units/timercamera/reference-redraw-front.png': '60b25a334a14252504f252bb454a39afdf53c4031fd7b677cfa8e04560039dca',
 'src/units/timerpwr/reference-redraw-back.png': '81e7a861266abc4c2b03fff04c23b9c3bb23ccc470cd17910d890f4c3eeaf700',
 'src/units/timerpwr/reference-redraw-controls.png': '3f387193d2f230fe8c456d964ed3be854c7d9db80a9d44c7ce2a87e93e8de9d1',
 'src/units/timerpwr/reference-redraw-ports.png': '63b386031413df45eb2d41f25b9d92bb0089b49273cdd9736be0d081883da0b2',
 'src/units/timerpwr/reference-redraw-title.png': '21449761e7ea0e92a417a53cf7c2e75ff68b894c9ca9b2578930f4e9316b3c60',
 'src/units/tmos-pir/reference-redraw-back.png': '27db9848a3017b5d5e45318fb2a56ea4b311c013b04f614e256a9c027bab1dfc',
 'src/units/tmos-pir/reference-redraw-front.png': 'beeb836e17ebaf46206ba4196512c954f41f79107eb4660c7ee87342f308627e',
 'src/units/tof/reference-redraw-back.png': '37f8adfd9355a4c922739eae4362d6757b6ee973d81df32479ab73a00b300a0b',
 'src/units/tof4m/reference-back.png': 'e89fc122d5a609093d7ad9ce7d2704e5acbd2a8ce3348e5e8ef7db342906862b',
 'src/units/tube-pressure/reference-redraw-back.png': '537b3b19c8cd09bcff8878442bb62e7aca45ff84e69a37e49c5640cf94698215',
 'src/units/tvoc/reference-redraw-back.png': 'dd13f0cef61321e8d46f8e55bc49a9dd6f85a0c1eaa3533943ff948e35ce1d76',
 'src/units/tvoc/reference-redraw-front.png': 'e4883e681081afcaa7f2ba67224064d4ef0df5772d7624ad3d03e0208387174e',
 'src/units/typec-to-grove/reference-redraw-back.png': '44ca3eaf84e4917835d3ff440b29e43b7372922d56b4f73b58b56f3dd8ad26cc',
 'src/units/typec-to-grove/reference-redraw-banner.png': 'c000a80b5bebf859c5db4324a6afae6d011fa23ed41284f5be1806042d4f0b2c',
 'src/units/typec-to-grove/reference-redraw-power.png': '7a7a31a06da6ef6694029c004bd677d59914d92e7511cbf889056b898180fed9',
 'src/units/uhf-rfid/official-back.png': 'da75a923d4419af4205250021375b4dba84d0f7b4f268787873169294d52f834',
 'src/units/uhf-rfid/reference-redraw-front.png': 'bb6ba2599411837286868844ad6d62939faacf3358d0a4ae1d0bada7af587d9f',
 'src/units/ultrasonic-i2c/official-back.png': '718b6c859a3ccbc166b4595ba44e4d63bbe503261f4c4258374b9b4dbd4962f0',
 'src/units/ultrasonic-io/artwork/back.png': '067973ae36a0c3c6c6069ccc59613b0371530d795227b16a8835f4311fb95ce3',
 'src/units/unit-396/reference-redraw-back.png': '034b401d032cef422d85a43bf0d1821befe6a1781cc4f6bfb1aaade06363f32a',
 'src/units/unit-id/reference-redraw-back.png': 'c998a3b56cdede56d080bbe3ca3c11a559fbe749ab5db46c13d3da1ec91c5f4a',
 'src/units/unit-id/reference-redraw-front.png': '26470aa83f8bcc14b4712b74973cb04f768a16665544a722bad00d52a41f3168',
 'src/units/unitv-m12/artwork/front.png': 'da12d3517e9846120aa720f6dd83d46975200419afbfbde6f487a327a04c0d4f',
 'src/units/unitv-m12/artwork/rear.png': 'c8addf92d886eff80f685de5d13c73008b22b3ca5e02ef319d1112024353c3d4',
 'src/units/unitv-ov7740/artwork/back.png': '851e857ddb5afecc4c39b9ab21760e744ee5402cd5d1b14a22edba26e62aac08',
 'src/units/unitv2-m12/artwork/rear.png': '78af0f014686286d39f54e3a8e3b0fc961ae7fc6c4efa2a047300cd930fbf1a9',
 'src/units/unitv2-usb/artwork/rear.png': '1de3d56f49580a61e0e0a1895440cd54ceea158e74d4e2e2cebff01020a5a1b7',
 'src/units/unitv2/artwork/rear.png': '72272097590fabd58e4079300236dcb7306b61987fb7f5baf04ed7bbc84d3a2d',
 'src/units/uwb/source-vector-back.png': '7b083871f4c838b70e4fc2be96d48690ff1ac928d2fcee10a0473fc6d54871df',
 'src/units/uwb/source-vector-front.png': '4b3d0dd0f375eb4cb70117549056818d7d41ad6db1607d3900d22a47eee9f904',
 'src/units/vibrator/reference-back.png': 'db892d47296ccdfd0e5da60effa3f5db4720e73ddc1a6c2f27521dcc273bd2ef',
 'src/units/vmeter/reference-redraw-back.png': '43391ff71d8e8639676533b06cdf2af84ddbd49692b3f32f6702d00d999965cc',
 'src/units/vmeter/reference-redraw-front.png': '725dc427bf79661c68882c191a312343dd3a9eba155e7534936795bdcdf964aa',
 'src/units/watering/reference-redraw-motor.png': '98caad348c74685123f36d903ce9df0dd603fc48510e8eb9cdafba73f5655371',
 'src/units/watering/source-vector-back.png': '9c1d2bbeab2f6a6d0e9cdde9b726162d237d823608f4ce5bd89798b9aa293fab',
 'src/units/weight-i2c/reference-redraw-back.png': '2413cb288369425f08ef8468dae7870f480e2ab1c9add53270ea5c87ba060736',
 'src/units/weight-i2c/reference-redraw-front.png': '6228ebc5bcde9e504aa0881d0928056b3c2fe25f062155b872a1789ac6becdd0',
 'src/units/weight/reference-redraw-back.png': 'a6f65fee21e1441291495fa7f2cecb91e8096264984b1d51fc071eb95e58e0e8',
 'src/units/weight/reference-redraw-front.png': '4a5e6862bc9cafbabd9ff5d0256b0deaead624831344230da8b90c852e942e97',
 'src/units/zigbee/reference-redraw-back.png': '3133315d418b42d0e784ab4c4e46c7b80d920bd6d756ae23742910e84059c180',
 'src/units/zigbee/reference-redraw-front.png': '86be7e2cbbe3e0dc21de73e938f1d38b3d320ac8ce15ae27bbbef33d751a144a'}
# These two Basic labels have no confirmed mounting location or runtime reference.
# Authenticate the public Git objects, but never redistribute unused artwork.
REVIEWED_UNMOUNTED_PNGS = {'src/devices/basic-v27/artwork/care.png': '15b4094abf62c85e711ed02ef71e320ef109126dad7e529e24a82136eadba35d',
 'src/devices/basic-v27/artwork/compliance.png': '7efa3a35c6eac5e211137687ab770b92ba8b4e6598aba3d495ee5bc9fe0dbcfd'}
REVIEWED_RUNTIME_LICENSES = {'src/devices/atoms3-lite/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/atoms3/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/atoms3r-cam/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/atoms3r-ext/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/atoms3r-m12/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/atoms3u/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/dial/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/stickc-plus/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/stickc/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea',
 'src/devices/stickt2/LICENSE-M5-Hardware.txt': '44611d917bece311f5c8eeffce83d8bf9e9ca3f815d262f694ff4a7996af50ea'}
# Exact public text closure reviewed at GUIDE_SOURCE_COMMIT. Never glob docs,
# research or artifacts: additions require source/hash/content/link review.
REVIEWED_GUIDE_FILES = {'artifacts/accel-op90-op180-expansion/progress.json': '16e2f3117ef495d07b5646e8fc1daba9ca1c3d95c4731de21e1108c8032d5868',
 'artifacts/adc-meter-expansion/progress.json': '161dd30d50e7eeb990ecc8a030653d29ad9e40f11ea010e27f890d254b7c51ba',
 'artifacts/audio-pressure-expansion/progress.json': '1777733a57d49d4d2e3afde89c26e912d93e58ad22638c8fcfd636a9d5ed1dd3',
 'artifacts/bldc-rca-puzzle-expansion/progress.json': 'a58ed63c82260bffdd4f80f14d71cccfe8d3e7d10518cb1436cca546b79db1f0',
 'artifacts/byte-joystick-unit-expansion/progress.json': '2e6a9b3bcdb0fe4bc209fa6731c820d5471b581dbab36d9cb44a9d3125ef338b',
 'artifacts/can-env-tof-unit-expansion/progress.json': 'd15e491f6c91c0176176de346781cce45e92e0a9c268fd518c0e2dd5b65ce9ac',
 'artifacts/dac-dds-kmeter-expansion/progress.json': '754fd7b1331e978c3a6a988bceb9014cdc1b318c0cfa882bec9cfa0aba4631f4',
 'artifacts/dcssr-ncir2-reflective-ir-expansion/progress.json': 'e7f551f106c2b42660713a006763e29b23427ab20b77c7667610e52f85926b68',
 'artifacts/display-co2-unit-expansion/progress.json': '2aa17677fb98cf59b799f731831157375db872660d491acc021c00a548b9fc34',
 'artifacts/earth-hall-qrcode-expansion/progress.json': '60894a4650ac7e81bd9c09bade42de701fc4e4fbcbb96e575ae93c6d870211b2',
 'artifacts/encoder-detail/public/review.json': 'e6af596349f060564803b7601a68bd151a07623c4bab26c348d86e6c946d2ce9',
 'artifacts/id-rf433-expansion/progress.json': '62d9229e80758953a8e4c08726235688534e48738d8fa68d3527343afe49f74a',
 'artifacts/imu-extio-acssr-expansion/progress.json': 'ce6b807892a9ba5be396826c5080c49dfe9da38805664c20b845221405e7cb98',
 'artifacts/interactive-unit-expansion/progress.json': '640d264bf0904adfe2d4c81e1028629e7fc57c2eabf63b574c3acaeba9082ee9',
 'artifacts/isolated-interface-expansion/progress.json': '3f5952e65d2cdc54f140cd58e8e4edf97a368e776e81c430abb027c4a557c473',
 'artifacts/laser-midi-expansion/progress.json': '36fb4c6e9768b502c0f863c1c380ba59d3c6c765524928f6c6bbcb5a5b545df9',
 'artifacts/multiport-unit-expansion/progress.json': '8b5de070691a8f72ab3b37bea39a9bbb1031199d06f431fb7f14335af17a554c',
 'artifacts/network-camera-synth-expansion/progress.json': '5b0e5ca65244ff2a20c0e098c8dee11fec35ba9bce95b4e607485baeee5a84c1',
 'artifacts/radio-gas-pressure-expansion/progress.json': 'b2ce5abc2a48e3eb8e1bfa779cc4ef9b64d7e374ed85469c927caa60bb30859f',
 'artifacts/ranging-presence-expansion/progress.json': '893619b1ab8c2caac61d75c1e64019405f02bbf963628debfc4612dae2d7425b',
 'artifacts/relay-dmx-unit-expansion/progress.json': 'b15208b4a3810714c480d224f9f40d14507fb718f708d4fdc76f65bdf23881c4',
 'artifacts/roller-mini-can-ina226-expansion/progress.json': 'a14fbd543b6a004e00fadd2a383459e61be9a1d7bda62ee40c9b67c82ebd5261',
 'artifacts/rotating-unit-expansion/progress.json': '542a3851db9cfb932cba497815b4e173b95f5b14baa3c189c49d155b559fec1b',
 'artifacts/rtc-fingerprint-audio-expansion/progress.json': '2b796d211177815866517c60d5a4dbc1a71592137ebf5cb8484627549ccd6c3c',
 'artifacts/step-asr-uhf-expansion/progress.json': 'd0ac5650c621b2921c86b01d33170f2eb039429ebb9f55d50a4041d3bd3a4645',
 'artifacts/terminal-tongue-closure/check.json': '64ff5f867331209a4180b1392201700ec2f7d43b81421b657c4c2d2684f59fc3',
 'artifacts/terminal-tongue-closure/repair.json': 'c0fd9f01445f77d5261cb59f7edb996ee0aefb026089b115478a8eb013f9a3a2',
 'artifacts/thermal2-flashlight-gps-expansion/progress.json': '1f22e90c29d17eeafbf21912c4737259c87b8df49dc8f506401df2e59b63412b',
 'artifacts/timer-encoder-nfc-expansion/progress.json': '5a0210f4f101218805b98796ddd1f633efe27c64dd970c6fc22c57e5eea1aa01',
 'artifacts/unit-expansion/progress.json': 'e217e15205323f6a5f182adb48304c158164dead11105711a946216c5cc9db20',
 'artifacts/unit-sticker-additions/progress.json': '2107b5990de47239cacee4185ea859de776e4fa0f42c7747604635621bb40e0e',
 'artifacts/unit-terminal-accessories/progress.json': '906aad149caa448f75b52c79e9955a7485ca428e49252d3ee3af6184a1ecffdb',
 'artifacts/watering-light-hbridge-expansion/progress.json': '5e200f66b3b833c91b122149b3bf6d5c9036423535af9aedb5bfb798f861b800',
 'docs/ACCEL-OP90-OP180-UNITS.md': 'b26a506541c9fb7ef39619b11872c9fb0f6639267079f06c46ae5fd66f172e3f',
 'docs/ADC-METER-UNITS.md': 'd35a5de2bc2ea03f5e863c265db285249cd1c9fb9fb9feb8835398bf07b7c724',
 'docs/ANGLE-MODEL-NOTES.md': '310f9a5b24543cdc12e487ba72c9f3c31fbac9c7b17aa02b551c91dfb48a0602',
 'docs/AUDIO-PRESSURE-UNITS.md': '37051ce3b03714819b74d921ccce91e1ed29df7b3cf4a51942300d57e04869a1',
 'docs/BLDC-RCA-PUZZLE-UNITS.md': '1d4008d33d59c70cb6ec807dc7c2ee388e06ab878ef3c524538739f0a4255959',
 'docs/CAN-ENV-TOF-UNITS.md': '6fb9ef50738241dab1df42dc8044d0e16ef42d2ccefcd0aa5df068e6458308d9',
 'docs/DAC-DDS-KMETER-UNITS.md': '93a42194a98ce8909ce2f94956f0bd9a6f5225305c277cff719a524f2dfbd18c',
 'docs/DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md': '49751ffe102faa1a77513633fbac681d93e872d3da2fd2c58c95902b25fdd0cb',
 'docs/DISPLAY-UNITS.md': '719adf8ed20ff9539fbb7c74714883cc4c50a2b00f808ddf677541e209fed07c',
 'docs/EARTH-HALL-QRCODE-UNITS.md': '1ee2540d6210cd871a2620a9aa92fc33458c62791189ee813e77611d23a4378c',
 'docs/GIT-SYNC-112-2026-10-26.md': '2d315252e7d95eecc92638ca9e4035051bcd4f05931ceadf1b2ec94a10e0ac96',
 'docs/GIT-SYNC-127-2026-10-26.md': 'cb1928f8d3437815c4e1aea014fef6a6b08d8450784773457c9ddb61157f8816',
 'docs/ID-RF433-UNITS.md': '12af1d293db5ce6e4cd88aaa72210462781aa8db7ada9b66fbe16903bd984d57',
 'docs/IMU-EXTIO-ACSSR-UNITS.md': 'd7a104cd6fe77f3a8386de08219f59d3df514a3113c20515928ca280494a0f87',
 'docs/INTERACTIVE-INPUT-UNITS.md': '2cdd6b245f023696d24aa618ba79dc835766a6d47285588d0c8e51b09185e5e1',
 'docs/ISOLATED-INTERFACE-UNITS.md': 'b352c3860fa927d48a13adeff440dfce7f7522d572332024a7a57c00e5855eb8',
 'docs/LASER-MIDI-UNITS.md': '2d1d9d8111f4f37412329e52ba55358354ad5bdca8b644363aa5314bc2053eec',
 'docs/LOCAL-EXPANSION.md': 'a95f8febdd3dce455d421024b9ad993376256de068e546f75d151a1266849f80',
 'docs/MULTIPORT-UNITS.md': 'c8f364203118901f64239c7eef2294aa516c3336e1fe9a1b0c2ba78a3dda5b8b',
 'docs/NCIR-MODEL-NOTES.md': '94eb9b74b05166b003c2740dad981410ca6464515bdc43e08a3001c82a883d32',
 'docs/NCIR-SOURCES.json': 'aea35d4e712b8a90685bbdf94ceaafd32df17da602f9955c276aeeb74f1b0f4a',
 'docs/NETWORK-CAMERA-SYNTH-UNITS.md': '2875dcbde5d8d9289f11dd47a3037e8019349d7a81c214512c4d92858396f68d',
 'docs/PCB-HOLE-WINDING.md': '24c95725a26ea380f47e3fc169fd7fe9de30d157942bcf7cbabee04e85d6db3e',
 'docs/RADIO-GAS-PRESSURE-UNITS.md': '08aeac6fa1aa07b7ece4cd2ce7732c2018324587e1c48b4ae8b2e749b950d4bf',
 'docs/RANGING-PRESENCE-UNITS.md': '32f8ffc26fbaccbba03781ff96250b745b226ea0880eacf8bf0ad6619e6b882e',
 'docs/RELAY-DMX-UNITS.md': '4574f281e62b5cc9cb154eee8614590fb01eed246c5c61c2fb3781e03f6e01de',
 'docs/ROLLER-MINI-CAN-INA226-UNITS.md': '7205ee4d0354a292c958401f4081d9b81aac0e2318009980bd0d2e3d8af52be3',
 'docs/ROTATING-UNITS.md': '23749e339617985b7c3cf25e0806a54a03c465a28c23d80889fcc14511db8cfb',
 'docs/RTC-FINGERPRINT-AUDIO-UNITS.md': '8acf33aa94451ca22bbd0c347d2790ad2861f537891aa2c9be3b8945e123e40f',
 'docs/STEP-ASR-UHF-UNITS.md': '2ecddeb28418a02dc1642a59e32982cfd08de5e33bbcca77db765787d180939f',
 'docs/STICKER-COVERAGE.md': '6beebff5046fb9bc5227e4ca2c5a6c5b81df0b782e295d30ab6804c1d4116be6',
 'docs/TERMINAL-TONGUE-CLOSURE.md': 'f22be8cfee38a04fc1765a6afcb0cc15e3bf1a6127752ad86b09e95d597cc532',
 'docs/THERMAL-MODEL-NOTES.md': 'b1ea3f20b67566a7fa91a5107aae713e4b2aefb81b3a21fce0c4f0769169d45e',
 'docs/THERMAL2-FLASHLIGHT-GPS-UNITS.md': '266a692e130c0c0979e8d1cd61cbf361162a66934dd56cf61a249a5eca5e922b',
 'docs/TIMER-ENCODER-NFC-UNITS.md': 'cb0a234a7e48a4551845741af938b4d686643123b3d7851db83af17434662c9c',
 'docs/UNIT-STICKER-ADDITIONS.md': 'd7033545dcc6c9fa64ccb3d842522fa2744d26d8646d05706ccc9ca44bb85e27',
 'docs/UNIT-TERMINALS.md': '4e5a42d0c32eca633ab3c90a7be57028ca2c07e228fefe58db83bb236309fe83',
 'docs/WATERING-LIGHT-HBRIDGE-UNITS.md': '52fc22b25c3f3d53c77f9a622976b0169f09fd29a2d30566d071a34fd788d3d8',
 'docs/research/2relay/STICKERS.md': '5713108d8fb2618f879cffa8234a4ce19877d50028f3c9f07f3e1205ebb04e2a',
 'docs/research/4relay/STICKERS.md': '26a212e9a56ae904b24ce65247d098ea45f77f824df4cae2f8e6503612962a47',
 'docs/research/8angle/artwork.md': 'aa9745d7b7f3c665b0143e32b78449ad140e69ee31ec004312e8eb22a5a14931',
 'docs/research/8servos/artwork.md': '6ae93c78bce7e9cfe78ad94c4185b7fa04903e372f05af91b9de53e522460422',
 'docs/research/acssr/README.md': 'c21aab94c05b4547bf797fd49ea538ebd2bdb7c5c5198f88bedf61da40ab472d',
 'docs/research/acssr/smoke.json': '84e38d64d95ba1d6bb0d6d335a2be79c434c1857744f88fa04fe643b5a8c1590',
 'docs/research/adc-v11/artwork.json': '1348e4f8be7ded574d73fadf79ad811b6ffd101f0db84e9ed85f41e14c67e86f',
 'docs/research/adc-v11/artwork.md': '002a3f99cef8b3e12d8c8099df9067b1fa0b0bdb32e22ad9685e65ce5044d9b7',
 'docs/research/asr/artwork.md': '420fb7cc594b553855922ed4ac44558ba96bdd5b576a435cca4e9e221d49affa',
 'docs/research/asr/modeling.md': 'd3977ee3081f52dccddcbe370a9d3595931945de4799723e674ef5265d022cd6',
 'docs/research/audioplayer/sticker-check.json': '801d803d2b17c8e56bbd1ee09668d70faaf913745c1eb9c22654f7e79441cbd7',
 'docs/research/audioplayer/stickers.md': 'd510031d7c193045f29663a9bb9a1301f79dab39a0482345a5bb8f3c93719254',
 'docs/research/bytebutton/artwork.md': '0a0819a6d13ebfb328bcc24d8adb32e17d9577cb6509724b9019f48726f5a44b',
 'docs/research/byteswitch/artwork.md': '671899777076c3900acebf36beeac098e52ee824d6413e043b31147ac6535e15',
 'docs/research/cams3-5mp/modeling.md': 'a870245e21a4b00dd1a40f7282e0029f7a7c4e190e2a5fbebcbbcbaf1bc27d7e',
 'docs/research/cams3-5mp/smoke.json': 'dfaf995de4fba50ad304ff98c75329a0ca96ec5e4206c73d4727e6afbb6576e8',
 'docs/research/cams3-5mp/sources.json': '9db1d767538a990bb14874c812d0657bbe2449f8883ce2eab23d2d41acda3959',
 'docs/research/can/STICKERS.md': '658171a18809218415f99d994923ba9bf45dc77b34345c79fba77995c5250989',
 'docs/research/co2/sticker-check.json': '3000927518d82f6e8d9b207e87cd9fd8516c473fdfd08279cec3f22e54ca3a53',
 'docs/research/co2/stickers.md': 'b8a0261b997618bcc12855ce2751e2b8fb2e026c3a3623b828edc3dc8bffcd2d',
 'docs/research/dac2/artwork.json': '820a5db5c84eb44c998b4157a5d2ba5af39b0539f1495b12729e1a82e6c10acc',
 'docs/research/dac2/artwork.md': 'c16cab3e2cec5871329b588a92ecfce3f0b41a21fd6a57438842fd8c778aa956',
 'docs/research/dac2/modeling.md': 'b74159933ad88150d4ac88ba595bdd25411f34be40403c2168ea91be873eb6e4',
 'docs/research/dac2/smoke.json': '2e81963da7c4b40d8f94298da2d59b3ca7a8fcf02819e1ff3b40d2594c185f1b',
 'docs/research/dac2/sources.json': '0c00f661fb3e1afd787a4f322c1c8e93a327ff72fad6509c82b673094740c763',
 'docs/research/dds/artwork.json': '861dd8ef8123e27ff41537d595664c14c60ca616cc60c7512c3a8375412c04fc',
 'docs/research/dds/artwork.md': '64f6a3f704721e6f63b8dbc64bd2667ac3feb5ba18fcd8798ef420d9adb73fb8',
 'docs/research/dds/modeling.md': '1e12646f823d9d223b064f05bfdad59497238cfa2ebdcffbcb6dd0d4b710914c',
 'docs/research/dds/smoke.json': '4496ac4b8b3244ec0528b11a2fc370fd70c89b1be2cc3ec68b675b0b2a7502b7',
 'docs/research/dds/sources.json': 'cb8ba17fa3fc15cfb40691371a8d1bd5be1a1c3a4eb519814f3e41e90bca4c1b',
 'docs/research/dlight/artwork.json': '457880210e5b791a17f02bd4b6dda7b2901176c07b56da9013548ee45f4d1c91',
 'docs/research/dmx/STICKERS.md': '8875c8c79b5a62faf0a16b4585d22e4e706ce7059981e12d681af49af38c20d3',
 'docs/research/earth/modeling.md': '0528dfea5f6cb35cf760c6fa29202f7fbe042ca0d5a4d63434285d78040dfc09',
 'docs/research/env-pro/STICKERS.md': 'e65cc6abc4d4c89d8090edf0af9b820c1b4e29d4db73b7a11af16e0bbce8431c',
 'docs/research/extio2/artwork.md': '6facebfbc47299c4f70379d3aa362f8b3724c7fd738557ca3894fb6eb9ac92c4',
 'docs/research/fader/artwork.md': '0b394d5acbf5a1c25bfd43c5eaec4542e6c17639acfa0630115b624ba8e8520c',
 'docs/research/fingerprint2/STICKERS.md': 'f82c65a9ffbd0395867d8a00c1052400f211a651158c2be7985aec4ba2254d3c',
 'docs/research/gesture/sticker-check.json': '751cb56b7bff87284a9adb15991559fa2cab36f6c214aaf8e84af34aa8e902fc',
 'docs/research/gesture/stickers.md': '4ad22d310f3cd63ef30b82c38c7cd1b9a20c93208d442366a48383254e8d117e',
 'docs/research/gps-v11/artwork.md': '987eb9fcd0af3e7e1766782f780fabc665d2ae6b265447b00ec0fb53e5f32255',
 'docs/research/hall/artwork.json': 'c4670bd46d0d63f0848a07df2cf3963db19af4c2dc263661c3d6bf86b278428b',
 'docs/research/hall/artwork.md': 'a3b66b278d8989429b82d220460a90c71b93188643fa44e677b20f3a1c999ee6',
 'docs/research/hall/modeling.md': '8a9cf211336bb529526e4380f2e4578fba946fe623f7669998fb1b7b60b66f93',
 'docs/research/hall/smoke.json': '2403a9cc8d8df943c19834f0604d3f0144fe887f3b1b0330f93c28f50b19a8a5',
 'docs/research/joystick2/artwork.md': '4f98ca30dae1766b3c7035f46d2d0cd76db5a88937d8bf1098c6698705e2d5d6',
 'docs/research/kmeter-iso-v11/artwork.json': '3c67ecc83bcb2299b68e16a9643fec38182a2478af14dbde4e8cc39249d0a365',
 'docs/research/kmeter-iso-v11/artwork.md': '6e1977601a571cfc2e9cbdaefe6a04606ee478db63c22a99e2e539e1bef4cb74',
 'docs/research/kmeter-iso-v11/modeling.md': '65dd513884e0c37198e47cbffa767011d188b8b3cb979c7fee5f2450bc95d37d',
 'docs/research/kmeter-iso-v11/smoke.json': '23f0e0ffd53673edd0ccd925df21730a9b02309520bfecdc153d11ac9e7d46c6',
 'docs/research/kmeter-iso-v11/sources.json': 'b31ce2be5782d97b8c943c8089dde35880928647a918adef5ae18f93ecef80a5',
 'docs/research/laser-rx/artwork.json': '1ac64ab5093a763c99aa41c467f4bb156d14906a4d9f09670fa2f9a9fd90b0a3',
 'docs/research/laser-rx/artwork.md': 'be8dc3b6b073b2ec95c8d9aa3ca7df20478a43954d3681d6afe981cd8be0aec5',
 'docs/research/laser-rx/modeling.md': '2cb39c329cb229c6651cd4570ec6d9a9576de54d5f765cc788c4161d7fea3514',
 'docs/research/laser-rx/smoke.json': '3438bfbd63302b8a349591d48b68686f777e06d0ad22f698357c73ff0fe37ab1',
 'docs/research/laser-tx/artwork.json': '089e4a98fe575e824ac1056c52840ba21406680c4b8f1b2b3b9acf075d321b36',
 'docs/research/laser-tx/modeling.md': '71888d046ede42454cc638e3aa7e558fce5c983d88f35fe09e86cbfc48fe5b8e',
 'docs/research/laser-tx/smoke.json': 'ef0920ee97e4b6507aa852f68d02c5dca6543d2f518ea0f5ac82b3df73df98f8',
 'docs/research/lcd/sticker-check.json': '37e9663a998006adcabacd32a7a1bac8c39dc632227b70cd031b50cbf2431412',
 'docs/research/lcd/stickers.md': '3e30f94744a6caa120c38a79466d1f38617ff43542362486023364db803cc4a8',
 'docs/research/midi/artwork.json': '931e35763daa10739cca1fd26640b269a499ba8ff3802f01a45d4d12632eab2f',
 'docs/research/midi/artwork.md': '0be5368ace099aa523b587f4fb114062ef8fe13d9acb27e33a4ab52525f5f4e1',
 'docs/research/midi/modeling.md': '046cb5757b33d658c9427c3f6f37046dd96374c5b14b8fac54cfebaf44f2f804',
 'docs/research/midi/smoke.json': 'aefe2aeaeb1b98f6ffe89f2cae24393271097f0aae35fb69c65cb689750cc20d',
 'docs/research/midi/sources.json': '84978426c40a18eba5b4337412aa329dcc8c539aa53ab44c094bf581141d77c4',
 'docs/research/mini-imu/artwork.md': 'af3a6e7d48e6f854a89d16c735ed7d5db6edbbb18d49ce8cb74bb4f0b8716970',
 'docs/research/mini-scales/artwork.md': '9a052ac7eb210d5084b1b32c68e3aa73a61586dea4b3d4f4eba5a781890baf66',
 'docs/research/nfc/artwork.md': '3b96c0d82305a7687c497f4e5bd4547a47ee2e3ce532e1f33789486477965fc8',
 'docs/research/oled/sticker-check.json': 'ab1ba8cddafcc2ea23294a88bffb34a2da1e15254948b9347b10d38329773434',
 'docs/research/oled/stickers.md': '30dad52de0d3b8c0fd802ea02e9474d854a540a43aac996e9677a2eadc29c1dc',
 'docs/research/pahub-v21/sticker-check.json': '97c3fe85f8b72a15c2dc0b3cbe50d5d17b1dcb150a97c7217a3ab79e7c0d41dc',
 'docs/research/pahub-v21/stickers.json': 'eb047bdadb3ebb716416071f0f8de175b5b732701edbe93a0d0310126b4b3308',
 'docs/research/pahub-v21/stickers.md': '2d8e9d523e6f9edce006cd2e4611a6494bdf1e6a4e0cab95c7df652d6ae5d1e4',
 'docs/research/pbhub-v11/sticker-check.json': 'eb14556dae4c75b643c775d05d0aa6d1d6f96694b9478703ab4d4136a8e73dae',
 'docs/research/pbhub-v11/stickers.json': 'dbdc5a965331b04707d5357fc414976147db871e61d9331674f17cfd3c0803b9',
 'docs/research/pbhub-v11/stickers.md': '6854b340d422fed136e7578713bc4daa863d9b1a4b6bd02d2c8e27724db04a39',
 'docs/research/poesp32/README.md': 'a936f8bf0e9029db70a161d0054b115dae5bb0028a661497d047eb1aebb767fc',
 'docs/research/poesp32/smoke.json': '525ca0c4fa9937876895a0568bc39850a37c45d1e6e315c2cdffa168f5d2b7cf',
 'docs/research/poesp32/sources.json': '0216369cfc7fa1210d1c29ab0b145089ccc4219381ab65ee65c832414656e41d',
 'docs/research/qrcode/artwork.json': '902f2e66ac01c2ef5e125af4c4b93cd94fbd9944a7f6b2f868fb03ad91865b7a',
 'docs/research/qrcode/modeling.md': '546ea5c7172aa0c08028c4a03d767e4964c96d82f149a1c3f606ca6492a2e0b6',
 'docs/research/qrcode/smoke.json': '610db0499042e6c0ad20e1e288d75346cfaef7d370d5408e8b2d9cb95a3d05e0',
 'docs/research/rollercan-lite/STICKERS.md': '0fa2c44b1761b45b9932eef774bcf0156493e52d9b751f00226fb745a435301d',
 'docs/research/rollercan/STICKERS.md': '78ab66c23cf79650255ced9175bbf621801f5afc4824370ec1dd004db9aef734',
 'docs/research/rtc/sticker-check.json': '6ff55aad644be29dea44a845fc065eb4bf353a01066faf875046d2bca52bf170',
 'docs/research/rtc/stickers.md': 'bc88ff39e6f56713ff76593f44060811ef66c2d8eea06e822a478693f6e54e5b',
 'docs/research/step16/artwork.json': '7f7ad5f55929afff8226ab0f4d7065ba2b47d8b745e85ad90194a8913b7c9a73',
 'docs/research/step16/modeling.md': '15ceabf64d9cb38ecdef11d94c3d0f334a12a71b0500c16934bca94573c17a12',
 'docs/research/step16/smoke.json': '750a0bc543fac7d50a9d88beaad0d672eb01a6f311aaf6ed9cd3b043ac11c2f7',
 'docs/research/step16/sources.json': 'dabef6cd275c507a8095585d13dca63964374dc2233038530167951bf530e266',
 'docs/research/synth/artwork.md': '0bec150f104976eb0ef48df2a25b3383bcaafa581b281f64177724a75baee921',
 'docs/research/tof4m/sticker-check.json': '5e1202875ced20bf1e6ba74b843fd26d2f0fd04faf60e4746f2389e084f8b0cd',
 'docs/research/tof4m/stickers.md': '7619f9b75e398c236de7e240bd2a9d3cfd8e25343ee089697ada533288dc8e18',
 'docs/research/tube-pressure/artwork.md': 'c3d68bc16b780d9312a8c5ff941d9c2f1166f1d07454fd66763ac05078035a52',
 'docs/research/uhf-rfid/artwork.md': 'ee21e04ffa01d669ba9901fd99415bace767374c1c25b34b292c5f870b42ce87',
 'docs/research/uhf-rfid/modeling.md': '899655fbcf3c21af962a5462c3a1d4dc52727f6c4f013b415d6d4737fd5dcefd',
 'docs/research/vibrator/sticker-check.json': '9f9d2e69bc2800702902cb4f011035f3594e674b2e2afbca9ba431579ee8ef8e',
 'docs/research/vibrator/stickers.md': '16ffac11ef6d6443fe3ed8e37f13fe11c81b91ecdab58e647695ee012943fb09',
 'docs/research/weight-i2c/artwork.md': '6bfdbb3fdb4df30f3d2bbc37d0d2100bcac9f141818938f8af9d2367efeb6fc9'}
GUIDE_ENTRY_FILES = {
    "docs/AGENT-INTEGRATION.md", "docs/INTEGRATION.md",
    "docs/GROVE-CABLE.md", "docs/VISUAL-MOTION.md", "THIRD_PARTY_NOTICES.md",
}
EXPLICIT_FILES = {
    "LICENSE", "THIRD_PARTY_NOTICES.md", "source-manifest.json",
    "catalog/products.json", "package.json", "package-lock.json",
    "docs/AGENT-INTEGRATION.md", "docs/INTEGRATION.md",
    "docs/GROVE-CABLE.md", "docs/VISUAL-MOTION.md",
}


def git(source: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *arguments])


def reviewed_runtime_assets(commit: str, names: list[str], files: dict[str, bytes],
                            unmounted: dict[str, bytes] | None = None) -> None:
    assets = {name for name in names if name.startswith("src/") and name.endswith(".png")}
    if not assets:
        return
    unmounted = unmounted or {}
    if unmounted and set(unmounted) != set(REVIEWED_UNMOUNTED_PNGS):
        raise ValueError("unmounted runtime PNGs differ from the explicitly reviewed allowlist")
    if commit != RASTER_SOURCE_COMMIT or assets != set(REVIEWED_RUNTIME_PNGS) | set(unmounted):
        raise ValueError("runtime PNGs differ from the explicitly reviewed commit/allowlist")
    notice = hashlib.sha256(files["THIRD_PARTY_NOTICES.md"]).hexdigest()
    if notice != RASTER_NOTICE_SHA256:
        raise ValueError("runtime PNG redistribution notice differs from the reviewed notice")
    for name in sorted(assets):
        data = unmounted[name] if name in unmounted else files[name]
        expected = REVIEWED_UNMOUNTED_PNGS[name] if name in unmounted else REVIEWED_RUNTIME_PNGS[name]
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"runtime PNG differs from reviewed Git object: {name}")
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
            raise ValueError(f"reviewed runtime asset is not a PNG: {name}")


def reviewed_guide_texts(commit: str, names: list[str], files: dict[str, bytes]) -> None:
    """Authenticate the exact reviewed public text closure before any writes."""
    if not REVIEWED_GUIDE_FILES:
        return
    if commit != GUIDE_SOURCE_COMMIT or not set(REVIEWED_GUIDE_FILES) <= set(names):
        raise ValueError("public guide texts differ from the explicitly reviewed commit/allowlist")
    patterns = {
        "MAC address": re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"),
        "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
        "provider credential": re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{12,})\b"),
        "credential assignment": re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|authorization|password|client[_-]?secret|secret[_-]?key)\s*[:=]\s*[\"']([^\"'\n]{8,})[\"']"),
        "private user path": re.compile(r"(?:/Users/[^/\s\"')]+|/home/[^/\s\"')]+|[A-Z]:\\Users\\[^\\\s\"')]+)"),
    }
    for name, expected in sorted(REVIEWED_GUIDE_FILES.items()):
        if not name.startswith(("docs/", "artifacts/")) or not name.endswith((".md", ".json", ".txt")):
            raise ValueError(f"reviewed guide is not an allowed public text path: {name}")
        data = files.get(name)
        if data is None or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"public guide differs from reviewed Git object: {name}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"reviewed guide is not UTF-8 text: {name}") from error
        if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
            raise ValueError(f"reviewed guide contains binary/control data: {name}")
        for category, pattern in patterns.items():
            if pattern.search(text):
                raise ValueError(f"reviewed guide contains prohibited {category}: {name}")
        for match in re.finditer(r"https?://[^\s<>)\"']+", text):
            try:
                url = urlsplit(match.group())
                hostname = url.hostname or ""
                private = bool(url.username or url.password) or hostname.endswith((".local", ".lan", ".internal"))
                try:
                    address = ipaddress.ip_address(hostname)
                    # Loopback development-preview examples contain no private endpoint.
                    private |= address.is_private and not address.is_loopback
                except ValueError:
                    pass
            except ValueError as error:
                raise ValueError(f"reviewed guide contains an invalid URL: {name}") from error
            if private:
                raise ValueError(f"reviewed guide contains a private/authenticated URL: {name}")
        if name.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"reviewed guide is not valid JSON: {name}") from error


def guide_resource_closure(files: dict[str, bytes]) -> dict[str, object]:
    """Close reviewed inline Markdown links; code and evidence JSON are leaves.

    This does not execute examples, follow JSON string references or validate
    Markdown anchors. Absolute URLs retain their upstream attribution.
    """
    links = re.compile(r'(?<!!)\[[^\]\n]+\]\(([^\s)]+)(?:\s+"[^"]*")?\)')
    pending = sorted(GUIDE_ENTRY_FILES)
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        if name not in files:
            raise ValueError(f"visual guide entry/reference is absent: {name}")
        if not name.endswith(".md"):
            continue
        text = files[name].decode("utf-8")
        matches = list(links.finditer(text))
        if len(matches) != len(re.findall(r"(?<!!)\[[^\]\n]+\]\(", text)):
            raise ValueError(f"unreviewed visual guide link expression: {name}")
        for match in matches:
            reference = match[1].strip("<>")
            url = urlsplit(reference)
            if url.scheme or url.netloc or not url.path:
                continue
            path = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
            if path not in files:
                raise ValueError(f"visual guide reference is absent from the reviewed snapshot: {name}: {reference}")
            pending.append(path)
    unused = set(REVIEWED_GUIDE_FILES) - visited
    if unused:
        raise ValueError(f"reviewed guide texts lack a root-guide reference: {sorted(unused)}")
    return {"status": "closed", "root_guides": sorted(GUIDE_ENTRY_FILES),
            "referenced_files": len(visited), "reviewed_additional_files": len(REVIEWED_GUIDE_FILES),
            "scope": "Inline Markdown non-image links; JSON/code are leaves; anchors not validated"}


def resource_closure(files: dict[str, bytes]) -> dict[str, object]:
    """Parse static ESM imports, then check the reviewed literal/template forms.

    SourceTextModule parses dependency requests without evaluating any module.
    Dynamic import() and import.meta URL forms are deliberately bounded: a new
    expression shape requires review instead of silently escaping validation.
    Template URL patterns cover all allowlisted matches, and browser checks
    separately exercise the actual runtime expressions and image decoders.
    """
    sources = {name: data.decode("utf-8") for name, data in files.items()
               if name.startswith("src/") and name.endswith(".js")}
    parser = """import {SourceTextModule} from 'node:vm';
let input=''; for await (const chunk of process.stdin) input+=chunk;
const sources=JSON.parse(input),result={};
for(const [name,source] of Object.entries(sources))
  result[name]=new SourceTextModule(source,{identifier:name}).dependencySpecifiers;
process.stdout.write(JSON.stringify(result));"""
    try:
        parsed = subprocess.run(
            ["node", "--no-warnings", "--experimental-vm-modules", "--input-type=module", "-e", parser],
            input=json.dumps(sources).encode(), capture_output=True, check=True,
        )
        dependencies = json.loads(parsed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ValueError("Node could not parse the public visual ESM dependency graph") from error
    external: set[str] = set()
    referenced_assets: set[str] = set()
    allowed_external = {"three", "three/addons/environments/RoomEnvironment.js"} | {
        "three/addons/" + name.removeprefix("examples/jsm/") for name in THREE_ADDONS
    }

    def resolve_local(name: str, reference: str) -> str:
        path = posixpath.normpath(posixpath.join(posixpath.dirname(name), reference))
        if not reference.startswith(("./", "../")) or not path.startswith("src/"):
            raise ValueError(f"visual resource escapes the runtime source tree: {name}: {reference}")
        return path

    dynamic_import = re.compile(r"\bimport\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)")
    asset_url = re.compile(r"\bnew\s+URL\s*\(\s*(['\"`])([^\n]*?)\1\s*,\s*import\.meta\.url\s*\)")
    for name, source in sources.items():
        dynamic = list(dynamic_import.finditer(source))
        if len(dynamic) != len(re.findall(r"\bimport\s*\(", source)):
            raise ValueError(f"unreviewed dynamic visual import expression: {name}")
        for reference in dependencies[name] + [match[2] for match in dynamic]:
            if reference.startswith(("./", "../")):
                path = resolve_local(name, reference)
                if path not in sources:
                    raise ValueError(f"visual JavaScript dependency is absent: {name}: {reference}")
            elif reference in allowed_external:
                external.add(reference)
            else:
                raise ValueError(f"unreviewed external visual dependency: {name}: {reference}")
        urls = list(asset_url.finditer(source))
        if len(urls) != len(re.findall(r"\bnew\s+URL\s*\(", source)):
            raise ValueError(f"unreviewed visual resource URL expression: {name}")
        for match in urls:
            reference = match[2]
            path = resolve_local(name, reference)
            if match[1] == "`" and "${" in path:
                # Current public sources use a filename or a numeric row only.
                expressions = re.findall(r"\$\{([^}]+)\}", path)
                if not expressions or any(not re.fullmatch(r"[A-Za-z_]\w*(?:\+1)?", value)
                                          for value in expressions):
                    raise ValueError(f"unreviewed visual resource template: {name}: {reference}")
                pattern = re.escape(path)
                for expression in expressions:
                    pattern = pattern.replace(re.escape("${" + expression + "}"), "[^/]+")
                matches = {candidate for candidate in files if re.fullmatch(pattern, candidate)}
            else:
                matches = {path} if path in files else set()
            if not matches or any(not candidate.endswith(".png") for candidate in matches):
                raise ValueError(f"visual PNG resource is absent: {name}: {reference}")
            referenced_assets.update(matches)
    assets = {name for name in files if name.endswith(".png")}
    if assets != referenced_assets:
        raise ValueError(f"runtime PNGs lack a reviewed resource reference: {sorted(assets - referenced_assets)}")
    return {"status": "closed", "javascript_files": len(sources),
            "runtime_pngs": len(assets), "external_dependencies": sorted(external),
            "template_scope": "All matching reviewed files; browser execution validates expression results"}


def apply_local_runtime_patches(files: dict[str, bytes], commit: str) -> list[dict]:
    """Apply only reviewed patches to exact upstream bytes, never local edits."""
    receipts = []
    for row in REVIEWED_LOCAL_RUNTIME_PATCHES:
        name, patch_name = row["target"], row["patch"]
        if commit != row["source_commit"]:
            raise ValueError("local runtime patch requires its reviewed upstream commit")
        if (not name.startswith("src/") or not name.endswith(".js")
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or not patch_name.startswith("patches/visual-models/")
                or any(part in {"", ".", ".."} for part in patch_name.split("/"))):
            raise ValueError("invalid local runtime patch target/path")
        before = files.get(name)
        if before is None or hashlib.sha256(before).hexdigest() != row["upstream_sha256"]:
            raise ValueError(f"local runtime patch upstream preimage differs: {name}")
        patch_path = ROOT / patch_name
        if patch_path.is_symlink() or not patch_path.is_file():
            raise ValueError("local runtime patch is absent or a symlink")
        patch = patch_path.read_bytes()
        if hashlib.sha256(patch).hexdigest() != row["patch_sha256"]:
            raise ValueError("local runtime patch differs from its reviewed hash")
        paths = subprocess.run(["git", "apply", "--numstat", "-"], input=patch,
                               capture_output=True, check=False)
        changed = [line.split("\t")[-1] for line in paths.stdout.decode().splitlines()]
        if paths.returncode or changed != [name]:
            raise ValueError("local runtime patch changes an unreviewed target")
        with tempfile.TemporaryDirectory(prefix="m5-model-runtime-patch-") as directory:
            root = Path(directory)
            target = root / name
            target.parent.mkdir(parents=True)
            target.write_bytes(before)
            for arguments in (["--check"], []):
                result = subprocess.run(["git", "apply", *arguments, "--whitespace=error-all", "-"],
                                        input=patch, cwd=root, capture_output=True, check=False)
                if result.returncode:
                    raise ValueError("reviewed local runtime patch does not apply cleanly")
            actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() or path.is_symlink()}
            if actual != {name} or target.is_symlink():
                raise ValueError("local runtime patch changed the closed file inventory")
            after = target.read_bytes()
        if hashlib.sha256(after).hexdigest() != row["effective_sha256"]:
            raise ValueError("local runtime patch effective file differs from its reviewed hash")
        files[name] = after
        receipts.append({"id": row["id"], "patch": patch_name, "patch_sha256": row["patch_sha256"],
                         "target": name, "scope": row["scope"], "adapted_from": row["adapted_from"],
                         "upstream": {"commit": commit, "sha256": row["upstream_sha256"], "bytes": len(before),
                                      "source_url": f"{PUBLIC_REPOSITORY}/blob/{commit}/{name}"},
                         "effective": {"sha256": row["effective_sha256"], "bytes": len(after)}})
    return receipts


def snapshot(source: Path, commit: str) -> dict[str, bytes]:
    resolved = git(source, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise ValueError("--commit must be a complete Git commit SHA")
    names = git(source, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    selected = [name for name in names if name in EXPLICIT_FILES
                or name.startswith("src/") and name.endswith(".js")
                or name in REVIEWED_RUNTIME_PNGS
                or name in REVIEWED_RUNTIME_LICENSES
                or name in REVIEWED_GUIDE_FILES
                or name.startswith("licenses/") and "/" not in name[len("licenses/"):]]
    missing = EXPLICIT_FILES - set(selected)
    if missing:
        raise ValueError(f"public snapshot is missing required files: {sorted(missing)}")
    files = {name: git(source, "show", f"{commit}:{name}") for name in selected}
    unmounted = {name: git(source, "show", f"{commit}:{name}")
                 for name in REVIEWED_UNMOUNTED_PNGS}
    reviewed_runtime_assets(commit, names, files, unmounted)
    for name, expected in REVIEWED_RUNTIME_LICENSES.items():
        if name not in files or hashlib.sha256(files[name]).hexdigest() != expected:
            raise ValueError(f"runtime license differs from reviewed Git object: {name}")
    guide_commit = GUIDE_SOURCE_COMMIT if REVIEWED_GUIDE_FILES else commit
    if guide_commit != commit:
        guide_names = git(source, "ls-tree", "-r", "--name-only", guide_commit).decode().splitlines()
        for name in sorted(REVIEWED_GUIDE_FILES.keys() | {path for path in GUIDE_ENTRY_FILES if path.startswith("docs/")}):
            files[name] = git(source, "show", f"{guide_commit}:{name}")
    else:
        guide_names = names
    reviewed_guide_texts(guide_commit, guide_names, files)
    upstream_closure = resource_closure(files)
    local_patches = apply_local_runtime_patches(files, commit)
    closure = resource_closure(files)
    guide_closure = guide_resource_closure(files)
    products = json.loads(files["catalog/products.json"])["products"]
    runtime_devices = {item["id"] for item in json.loads(RUNTIME_DEVICE_CATALOG.read_text())["devices"]}
    visual_controllers = [item["id"] for item in products if item["category"] == "controller"]
    manifest = {
        "schema_version": 1,
        "source_repository": PUBLIC_REPOSITORY,
        "source_commit": commit,
        "scope": "visual-only; firmware and electrical behavior belong to Device Service",
        "sync_command": f"python3 platform/tools/sync_visual_models.py --source /path/to/public/repo --commit {commit}",
        "three_version": json.loads(files["package.json"])["dependencies"]["three"],
        "controllers": visual_controllers,
        "visual_only_controllers": sorted(set(visual_controllers) - runtime_devices),
        "units": [item["id"] for item in products if item["category"] == "unit"],
        "resource_closure": closure,
        "upstream_resource_closure": upstream_closure,
        "local_runtime_patches": local_patches,
        "file_hash_scope": "files records effective vendored bytes; local_runtime_patches separately pins upstream preimages, patch bytes and effective results",
        "documentation_source_commit": guide_commit,
        "documentation_closure": guide_closure,
        "reviewed_guide_texts": {
            name: {"sha256": REVIEWED_GUIDE_FILES[name], "bytes": len(files[name]),
                   "source_url": f"{PUBLIC_REPOSITORY}/blob/{guide_commit}/{name}"}
            for name in sorted(REVIEWED_GUIDE_FILES)
        },
        "source_manifest_scope": "source-manifest.json is unchanged upstream provenance; its sourceCommit is a historical preparation baseline, not this vendor source_commit",
        "runtime_assets": {
            "kind": "product sticker PNGs",
            "redistribution_notice": "THIRD_PARTY_NOTICES.md#product-sticker-rasters",
            "notice_sha256": hashlib.sha256(files["THIRD_PARTY_NOTICES.md"]).hexdigest(),
            "license_scope": "Provider permission for public distribution; images and marks retain owner rights, not project MIT",
            "files": {name: {"sha256": REVIEWED_RUNTIME_PNGS[name], "bytes": len(files[name]),
                             "source_url": f"{PUBLIC_REPOSITORY}/blob/{commit}/{name}"}
                      for name in sorted(files) if name.endswith(".png")},
        },
        "excluded_runtime_assets": {
            name: {"sha256": expected, "reason": "Basic label mounting location unconfirmed; no runtime reference"}
            for name, expected in REVIEWED_UNMOUNTED_PNGS.items()
        },
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())},
    }
    index = {item["id"]: {key: item[key] for key in
                          ("id", "category", "name", "sku", "integration") if key in item}
             for item in products}
    files["runtime-index.js"] = (
        "// Generated by platform/tools/sync_visual_models.py from the pinned public catalog.\n"
        "export const MODEL_METADATA = Object.freeze(" + json.dumps(index, ensure_ascii=False) + ");\n"
        "export const MODEL_DEVICES = Object.freeze(" + json.dumps(manifest["controllers"]) + ");\n"
        "export const UNIT_MODELS = Object.freeze(" + json.dumps(manifest["units"]) + ");\n"
    ).encode()
    files["vendor-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    files["UPSTREAM.md"] = (
        "# Public visual model snapshot\n\n"
        f"Source: {PUBLIC_REPOSITORY}\n\nCommit: `{commit}`\n\n"
        "Copied from Git objects with explicit file/hash allowlists. Upstream worktree changes and "
        "private research are never copied. A separate reviewed local runtime patch layer preserves "
        "mainline pause/resume rendering on the upstream hidden-viewport fit fix. "
        "`vendor-manifest.json.local_runtime_patches` pins each upstream preimage, patch file "
        "and effective result; `files` hashes the effective bytes. Both upstream and patched "
        "runtime resource closures are checked. Reviewed public guide/provenance texts "
        f"remain pinned separately at `{guide_commit}` and preserve their source bytes "
        "and close relative links in the bundled guides. "
        "`vendor-manifest.json` records each source file and the reviewed guide closure. "
        "The unchanged upstream `source-manifest.json` records provenance; its "
        "`sourceCommit` is a historical preparation baseline, not this snapshot Git pin.\n\n"
        "Preserve `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` when redistributing. "
        "Reviewed product sticker PNGs, including source-vector rasters and authorized "
        "reference redraws, retain the provider-permission notice and per-file hashes. "
        "Artwork and marks retain their original rights and are not relicensed as MIT; official remote "
        "photos, vectors and generators are not bundled. All models are visual "
        "shells: firmware, controller, bus and sensor evidence come from this project's "
        "Device Service.\n\n"
        "This source uses the site's single Three.js 0.186.1 import-map instance. "
        "Load `src/loaders.js` to keep models lazy; do not import `src/index.js` in the "
        "first-screen bundle.\n\n"
        "Update explicitly with the `sync_command` in the manifest, inspect its diff, "
        "then run `node platform/tests/test_model_shell.mjs` and the browser integration "
        "probe. Use `--check` to confirm a reproducible snapshot.\n"
    ).encode()
    return files


def three_addon(files: dict[str, bytes], check: bool) -> None:
    """Keep the import-map's existing single Three instance and locked addons."""
    dependency = json.loads(files["package-lock.json"])["packages"]["node_modules/three"]
    metadata_path = DESTINATION / "three-addon-manifest.json"
    if check:
        metadata = json.loads(metadata_path.read_text())
        if metadata["package_integrity"] != dependency["integrity"]:
            raise SystemExit("Three.js addon differs from the pinned package")
        expected_addons = {name: str(path.relative_to(ROOT)) for name, path in THREE_ADDONS.items()}
        actual_addons = metadata.get("addons", {})
        if set(actual_addons) != set(expected_addons):
            raise SystemExit("Three.js addon inventory differs from the reviewed dependency graph")
        for name, target in expected_addons.items():
            entry = actual_addons[name]
            if entry.get("destination") != target or entry.get("sha256") != hashlib.sha256((ROOT / target).read_bytes()).hexdigest():
                raise SystemExit(f"Three.js addon differs from the pinned package: {name}")
        for name, expected in metadata.get("shared_three_files", {}).items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise SystemExit(f"shared Three.js dependency differs: {name}")
        return
    # Downloaded archive stays in memory; no node_modules or upstream worktree
    # content is trusted. npm's lockfile SHA512 authenticates the exact archive.
    with urllib.request.urlopen(dependency["resolved"], timeout=30) as response:
        archive = response.read()
    actual = "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode()
    if actual != dependency["integrity"]:
        raise SystemExit("Three.js archive integrity mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        addons = {name: package.extractfile("package/" + name).read() for name in THREE_ADDONS}
        shared = {}
        for source, target in {
            "build/three.core.js": "platform/web/vendor/three/three.core.js",
            "build/three.module.js": "platform/web/vendor/three/three.module.js",
            "examples/jsm/environments/RoomEnvironment.js": "platform/web/vendor/three/addons/environments/RoomEnvironment.js",
        }.items():
            expected = hashlib.sha256(package.extractfile("package/" + source).read()).hexdigest()
            if hashlib.sha256((ROOT / target).read_bytes()).hexdigest() != expected:
                raise SystemExit(f"shared Three.js file must match {dependency['version']}: {target}")
            shared[target] = expected
    for name, path in THREE_ADDONS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(addons[name])
    metadata = {"package": "three", "version": dependency["version"],
                "package_url": dependency["resolved"], "package_integrity": actual,
                "source_path": THREE_ADDON,
                "destination": str(THREE_DESTINATION.relative_to(ROOT)),
                "sha256": hashlib.sha256(addons[THREE_ADDON]).hexdigest(), "shared_three_files": shared,
                "addons": {name: {"destination": str(path.relative_to(ROOT)),
                                  "sha256": hashlib.sha256(addons[name]).hexdigest(), "bytes": len(addons[name])}
                           for name, path in THREE_ADDONS.items()}}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--commit", default=PINNED_COMMIT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = snapshot(args.source, args.commit)
    existing = {str(path.relative_to(DESTINATION)) for path in DESTINATION.rglob("*") if path.is_file()}
    stale = existing - set(files) - {"three-addon-manifest.json"}
    if stale:
        raise SystemExit(f"unmanaged or removed files require explicit review: {sorted(stale)}")
    differences = [name for name, data in files.items()
                   if not (DESTINATION / name).is_file() or (DESTINATION / name).read_bytes() != data]
    if args.check:
        if differences:
            raise SystemExit(f"visual snapshot differs: {differences}")
        three_addon(files, check=True)
        print(f"visual snapshot OK: {args.commit}, {len(files)} files and pinned Three addon")
        return 0
    for name in differences:
        path = DESTINATION / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[name])
    three_addon(files, check=False)
    print(f"visual snapshot synced: {args.commit}, {len(differences)} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
