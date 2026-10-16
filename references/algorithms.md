# 算法切图 · 实现要点与出处

本文记录 slice.py 中四个算法子命令的**实现原理、参数含义、调参建议**，以及参考的开源项目，便于后续维护与扩展。

## 参考项目（GitHub）

| 项目 | 借鉴内容 |
|---|---|
| [AstroGolem224/Sprite-Sheet-Cutter-Tool](https://github.com/AstroGolem224/Sprite-Sheet-Cutter-Tool) | 网格自动检测（分隔线 + 白缝 profile）、tight-crop + 等比缩放、批处理目录结构 |
| [EricsonWillians/Sprite-Extractor](https://github.com/EricsonWillians/Sprite-Extractor) | 轮廓模式（Contour）与网格模式分离、pHash 去重、空间重叠判别「同图不同位」 |
| [tanakornon/background-remover](https://github.com/tanakornon/background-remover) | OpenCV floodFill 去背景、阈值上下限、批处理、自动裁透明边 |
| [7BEII/Comfyui_PDuse](https://github.com/7BEII/Comfyui_PDuse) | **「从边缘泛洪」是核心技巧**：背景定义为「与边缘连通的白」，元素内部白色因不连通而安全 |
| [Jonny-zhou/background-remover](https://github.com/jony-zhou/background-remover) | 感知加权颜色距离、边缘羽化思路 |
| [sethmlarson/sugarcookie](https://sethmlarson.dev/cutting-spritesheets-like-cookies-with-python-and-pillow) | 纯 Python 连通域 flood fill + min-dim 过滤 + 2^n 对齐 |
| [JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash) | 感知哈希（pHash）去重 |
| [scikit-image label 示例](https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_label.html) | Otsu 阈值 + 二值闭运算 + `clear_border` 去边界伪影 |

---

## 1. `detect` — 连通域标记（算法切图首选）

**原理**：把 alpha 通道二值化 → 连通域标记 → 每个连通块求 bbox → 逐个裁出。
本质是「让算法自己找元素边界」，不依赖规则排布，**大小不一、位置随机的元素也能切干净**。

**关键参数**
- `--min-size`（默认 8）：元素最小边长。太小的碎块会并入相邻元素或被丢弃——小图标密集排布时可适当调小。
- `--alpha-threshold`（默认 10）：alpha 判定阈值。半透明素材（阴影、渐隐）需调低（如 1~5）。
- `--connectivity`（4或 8，默认 8）：8 邻域更宽松，适合斜向相邻的元素；4 邻域更严格，会把斜接元素判为两个。

**产出**：切图+ `manifest.json`（记录每个元素的 x/y/w/h，便于后续按坐标回溯、复原）。

**实现**：优先用 `scipy.ndimage.label + find_objects`；无 scipy 时回退纯 Python flood fill。

## 2. `grid-detect` — 智能网格检测

**原理**：把图像投影成行/列 profile → 找「缝隙」区间 → **格数 = 内部缝数 + 1**。
- 白缝模式（`--mode light`，默认）：间隙为近白，AI 生成的雪碧图常用。
- 深色分隔线模式（`--mode dark`）：间隙为深灰/黑线，手工 UI 图常见。

**⚠️ 关键坑（务必知道）**：**图像边缘那圈白边是外边距，不是格间分隔**。
必须剔除紧贴边缘的缝，否则 3×3 会被误判成 4×4。代码里用 `edge = 2%` 宽度做此过滤。

**参数**
- `--threshold`（默认 230）：近白阈值。米黄/浅灰底可降到 200~215；过low 会开始吃掉元素内的亮部。
- `--line-ratio`（默认 0.85）：该行/列判定为「缝」所需的像素占比。分隔线更细可降到 0.7。
- `--force`：跳过交互确认直接切。检测不准时手动输入如 `4x4` 覆盖。

## 3. `debg` — 边缘种子洪水填充去背景

**原理（最值得记住的一点）**：背景定义为**「与图像边缘连通的纯色区」**。
从四边种子向内 BFS 填充 → 触到的纯色像素变透明。
因为元素内部的同色区域（如眼珠、白发、白字）与边缘**不连通**，不会被泛洪波及→ **内部白色完整保留**。

这正是它比「全局阈值去白」高明的地方：全局阈值会把元素内的白色也干掉；而分割模型（BiRefNet/rembg）对扁平色边缘反而不如数学精确的 flood fill。

**参数**
- `--tolerance`（默认 25）：颜色容差。纯色底可 10；渐变底/压缩噪点可 30~40。
- `--min-consistency`（默认 0.42）：边缘与背景色的接近比例下限。**边缘一致性不足时直接放弃并提示改用 rembg/AI**，避免在复杂背景上乱切一通。
- `--trim`：去背后自动裁透明边。

**局限（诚实说明）**：渐变背景、柔和投影底、复杂纹理会切不干净——这类应改用 rembg 或 AI 抠图。

## 4. `dedup` — 感知哈希去重

**原理**：pHash 对视觉相似图像产生相似哈希，汉明距离 ≤阈值判为重复。
**用途**：切完后一堆图里挑出**真重复**（省包体）；同时用位置信息区分「同一图出现在不同位置」vs「真重复」。

**参数**：`--threshold`（默认 5，越小越严格）。

**依赖**：`imagehash`（可选装）。

---

## 选型速查

| 素材形态 | 用哪个 |
|---|---|
| 元素大小不一、位置随机 | `detect` |
| 规则雪碧图 / 已知行列 | `grid` |
| 规则但不知行列（AI 生成图） | `grid-detect` |
| 纯色底要去透明（保内部同色） | `debg` |
| 复杂背景要抠图 | rembg / AI 抠图（`debg` 不行） |
| 切完想去重 | `dedup` |
| 统一尺寸/留白对齐 | `adapt` / `batch` |

## 依赖

- 必需：Pillow
- `detect` 加速（可选）：scipy
- `debg` 必需：numpy
- `dedup` 必需：imagehash

安装：`pip install Pillow numpy scipy imagehash`