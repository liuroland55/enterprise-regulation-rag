# 应用图标

Tauri 打包（`tauri build`）需要以下图标文件，请在正式构建前放入本目录：

- `32x32.png`
- `128x128.png`
- `128x128@2x.png`
- `icon.icns`（macOS）
- `icon.ico`（Windows）

可使用 Tauri CLI 从一张源图自动生成：

```bash
npm run tauri icon path/to/source-icon.png
```

> 说明：本目录当前仅含占位说明文件，开发模式（`tauri dev`）不强制要求图标，
> 但 `tauri build` 会校验上述文件是否存在。
