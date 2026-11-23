---
name: photocraft-cli
description: "Use the locally installed PhotoCraft CLI to create or edit images and layered PSD files, export formats, and batch-process pictures in the background. This is the user's preferred tool for image and PSD processing on this Windows computer."
---

# PhotoCraft CLI

The user requested PhotoCraft for future image and PSD processing. Use its headless CLI for supported operations unless the user specifies another tool. Do not substitute another image editor just because PhotoCraft is absent from the current process's PATH.

## Local installation

Official repository: https://github.com/storytold/photocraft

Installed: Windows x64 portable release. Both executables are Authenticode-signed.

```powershell
$photoCli = '<PhotoCraft 安装目录>\photocraft-cli.exe'
& $photoCli --version
& $photoCli --help
```

The desktop executable `photocraft.exe` is beside the CLI. The install directory was added to the user's PATH; processes already running may still require the absolute path above. No desktop window or server is needed for `run`, `convert`, `info`, or `batch`.

If an upgrade changes this location, search the PhotoCraft install directory for `photocraft-cli.exe` and read that version's help.

## Discover before editing

Use the installed executable's documentation as the source of truth:

```powershell
& $photoCli run --help
& $photoCli commands --json --filter 'image.imageSize'
& $photoCli commands --json --filter 'type.create'
```

`commands --json` returns entries with `id`, `params`, `needsDocument`, and `enabled`. The installed release has 940 engine commands. A command disabled because no document is open can become enabled after opening or creating a document. Inspect parameter documentation for the requested operation rather than guessing Photoshop menu parameters.

| Subcommand | Purpose |
|---|---|
| `info FILE --compact` | Inspect dimensions, mode, depth, layer tree, editable text, and warnings as JSON. |
| `convert IN OUT` | Convert formats, chosen by output extension. JPEG/WebP quality uses `--quality 1..100`; TIFF retains layers only with `--tiff-layers`. |
| `run FILE ... --out OUT` | Open, execute ordered `--cmd ID --params JSON` pairs, then save. |
| `run --new JSON ... --out OUT` | Create a document using `file.new` parameters, optionally edit, then save. |
| `batch --actions FILE --in DIR --out DIR` | Replay JSON actions or Photoshop `.atn` files on a directory. Read help for named action sets. |
| `droplet FILE.pcdroplet FILE-OR-DIR...` | Run a saved droplet. |
| `commands --json --filter TEXT` | Discover command IDs and parameter descriptions. |
| `serve` / `mcp` | Persistent headless JSON-lines or MCP session; optional authenticated bridge to the desktop app. |

## Working patterns

In PowerShell, use objects and `ConvertTo-Json -Compress` for parameters and argument arrays for multiple operations. Check `$LASTEXITCODE` after each native call; PowerShell's error preference alone does not detect a CLI failure.

```powershell
$photoNew = @{width=960;height=540;background='#f5f2e9';resolution=72;name='Example'} | ConvertTo-Json -Compress
$photoText = @{x=64;y=160;text='Hello';font='Segoe UI';size=36;color='#202e2b'} | ConvertTo-Json -Compress
& $photoCli run --new $photoNew --cmd type.create --params $photoText --out '<工作目录>\example.psd'
if ($LASTEXITCODE -ne 0) { throw 'PhotoCraft creation failed' }
& $photoCli convert '<工作目录>\example.psd' '<工作目录>\example.png'
if ($LASTEXITCODE -ne 0) { throw 'PhotoCraft export failed' }
& $photoCli info '<工作目录>\example.psd' --compact
```

Useful families: `image.imageSize`, `image.crop`, `image.canvasSize`, `image.adjustments.*`, `layer.newAdjustmentLayer.*`, `layer.setProps`, `layer.layerMask.*`, `layer.smartObjects.*`, `type.create/edit/setStyle`, `shape.create/edit`, `select.*`, and `filter.*`.

- `file.new` supports RGB/gray/CMYK/Lab, depth 8/16/32, background white/black/transparent/hex, resolution, and name. Read its full schema for profiles and bounds.
- Point text uses a baseline anchor in `x,y`; `size` is points. Shapes use `rect:[x,y,width,height]`. Read each schema for colors, transforms and other options.
- Save an editable PSD when layers matter, then export the display image separately. Inspect the PSD after saving to verify layer types and text remain editable.
- Preserve source files by writing a separate output. The CLI refuses output equal to input unless `--in-place` is supplied; use that option only when replacement is requested.
- Read warnings. A flattened-layers warning is expected for PNG/JPEG exports; missing-font and unsupported-feature warnings need to be assessed for the actual task. Do not claim all PSD features round-trip perfectly from this smoke test.
- Verify output dimensions and warnings with `info`, and visually inspect the final raster with `view_image` before delivering.
- For a multi-request headless session, `serve --automation-read-root ABS_DIR --automation-write-root ABS_DIR` speaks JSON lines on stdio. Read `serve --help`; automation file access is denied for any omitted direction. Desktop bridging and TCP are optional and unnecessary for ordinary background editing.

## Verified example

A smoke-test script creates an eight-layer 960x540 RGB PSD using shapes and editable text, exports PNG, and reopens both; the result was visually verified.

Outputs are the test PSD and exported PNG in a dedicated test folder. The same folder contains the installed release's `commands.json`, `cli-help.txt`, creation log, and document inspections. For new tasks, query the live CLI when the saved catalog may be outdated.
