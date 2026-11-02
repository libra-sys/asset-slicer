# asset-slicer

A local-first toolkit and Codex/WorkBuddy skill for preparing reusable visual assets from images, PDFs, spritesheets, and approved slide designs.

## What it does

- Crop transparent margins and split known grids or separated alpha components.
- Convert PDF pages to images, mask selected areas, normalize images to consistent cards, and deduplicate assets.
- Support optional image-generation API workflows through local configuration.
- Document a semantic, page-by-page workflow for turning an approved slide visual into individually movable assets and editable native text.

## Important limitation

`detect` finds connected opaque regions; it does not understand semantic objects. It cannot infer that a region is a button, person, panel, certificate, or title. For slide decomposition, identify each object and its source bounds first, isolate it with a mask or recover the original asset, then use local algorithms for the appropriate crop. Rebuild ordinary copy as native text and reuse original evidence images. Do not use fixed grid slicing of a complete slide as a substitute for element extraction.

## Install

```powershell
python -m pip install Pillow numpy scipy imagehash pymupdf
```

Run a local command, for example:

```powershell
python scripts/slice.py detect .\input.png --min-size 200
python scripts/slice.py pdf2png --path .\materials --outdir .\mats
```

Run `python scripts/slice.py --help` for available commands. Some commands require optional dependencies listed above.

## Optional image generation

Local slicing does not need an API key. For `artgen`, copy `scripts/config.example.json` to `scripts/config.json`, fill it locally, and never commit the real config. `CONTEST_PPT_CONFIG` can point to another local config file. The placeholder config is not usable as-is.

## Skill installation

Copy `SKILL.md` and `references/` into your agent's skill directory as `asset-slicer/`. Keep the Python utility available at `scripts/slice.py` if you want to run the commands from the skill.

See [SKILL.md](SKILL.md) for the full workflows and [approved-slide-slicing.md](references/approved-slide-slicing.md) for the semantic extraction, manifest, and reconstruction protocol.

## License

MIT. See [LICENSE](LICENSE).
