# asset-slicer

WorkBuddy skill · 切图 / 规格化 / 出图工具。

把设计稿、图片、PDF 材料拆成可继续编辑的资产：

- **切图**：`detect`（连通域，元素大小不一/位置随机首选）/ `grid` / `grid-detect`（智能推断行列）/ `trim`（裁透明空边）/ `debg`（边缘种子洪水填充去背）/ `dedup`（感知哈希去重）
- **材料流水线**：`pdf2png`（PDF 逐页转 PNG）/ `mask`（隐私打码，按比例）/ `cards`（批量统一规格卡片）/ `spec`（按 spec.json 落位留白/安全区/九宫格）
- **出图**：`artgen`（调图片生成 API，出图结果可直接被 detect/grid 切）

完整用法、参数调优与踩坑记录见 [`SKILL.md`](SKILL.md)。

## 快速开始

```bash
pip install Pillow numpy scipy imagehash pymupdf
python scripts/slice.py detect input.png --min-size 200
```

## 配置（仅 artgen 出图需要）

复制 `scripts/config.example.json` 为 `scripts/config.json` 并填入密钥：

```json
{ "供应商": { "listenhub-image": { "api_key": "YOUR_KEY", "base_url": "https://..." } } }
```

也可用环境变量 `CONTEST_PPT_CONFIG` 指定配置文件路径。本地切图命令（trim/grid/detect/debg/mask/cards…）无需任何 API。
