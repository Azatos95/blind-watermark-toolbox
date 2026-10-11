# 盲水印工具箱 v0.2

给 [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) 做的中文图形界面，已打包为**单文件免安装 exe**。

> **算法核心与全部鲁棒性来自原作者 郭飞 (guofei9987)**，本仓库只提供 GUI 与打包工程，MIT 协议。
> 如果这个工具帮到你，请把 ⭐ 给[原项目](https://github.com/guofei9987/blind_watermark)。

---

## 下载

下载下面的 `盲水印工具箱.exe`，双击即可运行，**无需安装 Python**。

## 功能

- **三个完全独立的标签页**：① 嵌入文字水印 ② 嵌入图片水印 ③ 提取水印 —— 各自控件与按钮互不干扰。
- **拖拽载入**：图片直接拖进窗口即可；图片水印页连续拖两张 = 原图 + 水印图。
- **傻瓜式**：每页只有一块拖拽区 + 一个主按钮；密码默认 `123`；实时提示「占用 N bit / 该图最多可放约 M bit」，超容量提前预警。
- **默认输出路径**：自动存到 `桌面\盲水印输出`，文件名自动推导；桌面不可写时逐级回退。
- **参数不丢**：嵌入后自动生成同名 `xxx.bwm.json`（记录版本、密码、水印长度/尺寸、原文），提取时拖入成品图**自动回填**，不用记参数。
- **中文路径可用**：突破 OpenCV 不支持非 ASCII 路径的限制。
- **错误密码不崩溃**：给出中文提示而不是报错堆栈。
- **响应式界面**：随窗口缩放自动重排。
- **可自检**：`盲水印工具箱.exe --selftest` 会验证本机能否正常嵌入/提取（含拖拽链路）。

## 界面

| ① 嵌入文字水印 | ② 嵌入图片水印 | ③ 提取水印 |
|---|---|---|
| ![文字](https://raw.githubusercontent.com/Azatos95/blind-watermark-toolbox/main/docs/screenshots/tab1-text.png) | ![图片](https://raw.githubusercontent.com/Azatos95/blind-watermark-toolbox/main/docs/screenshots/tab2-image.png) | ![提取](https://raw.githubusercontent.com/Azatos95/blind-watermark-toolbox/main/docs/screenshots/tab3-extract.png) |

## 用法

### ① 嵌入文字水印
拖入原图 → 输入要隐藏的文字 → 密码保持默认 `123` → 点「开始嵌入文字水印」。

### ② 嵌入图片水印
先拖**原图**，再拖**水印图**（建议黑白稿）→ 点「开始嵌入图片水印」。

### ③ 提取水印
拖入带水印的图片 → 若同目录有 `.bwm.json` 参数会自动填好 → 点「开始提取水印」。
手动填时：文字水印填 **bit 长度**，图片水印填 **宽x高**（如 `100x100`）。

## 必须知道的限制（源自原项目的算法特性）

- **容量上限**：每 4×4 DCT 块藏 1 bit，约 `(W/8)×(H/8)`。如 1616×1078 图约 13,600 bit。
- **提取必须知道水印长度**，忘了就解不出来（本工具用 `.bwm.json` 解决这一点）。
- **两枚密码在嵌入/提取时必须完全一致**，库版本也要一致。
- **输出必须无损**（PNG/BMP/TIFF）；JPEG 有损压缩会抹掉水印。
- 抗截图/裁剪/旋转/缩放/亮度/椒盐噪声/遮挡；但**微信等有损压缩过的图通常提取失败**。

## 文件校验

- 文件名：`盲水印工具箱.exe`
- 大小：64,064,462 字节（约 61.1 MB）
- SHA256：`3A193C4F7C6BB3B42B4AF4854C0107343E86032B180439ADBF09753760F52D95`
- 内置版本信息：`0.2.0.0`，版权栏含原作者署名

> 校验方法（PowerShell）：
> ```powershell
> Get-FileHash .\盲水印工具箱.exe -Algorithm SHA256
> ```

## 注意

- **未做代码签名**，首次运行 Windows SmartScreen 会提示「未知发布者」→ 选「更多信息 → 仍要运行」。
  部分杀软可能对 PyInstaller 打包的程序误报，可加入信任。
- 请不要把 exe 放在受限沙箱/只读目录里运行（单文件模式需要向 `%TEMP%` 解压）。
- 若用杀软或系统策略限制了 `%TEMP%` 写入，可改用 onedir 方式自行打包。

## 开源协议

MIT License。`LICENSE` 中保留的是**原项目**的版权声明 —— `Copyright (c) 2019 郭飞 (guofei9987)`，
这是 MIT 协议对二次开发的强制要求。本仓库新增的 GUI/打包工程版权归 Azatos95。

第三方依赖与协议见 [THIRD_PARTY_NOTICES.md](https://github.com/Azatos95/blind-watermark-toolbox/blob/main/THIRD_PARTY_NOTICES.md)。

## 致谢

感谢 **[郭飞 (guofei9987)](https://github.com/guofei9987)** 开源 [blind_watermark](https://github.com/guofei9987/blind_watermark) ——
它用 DWT + DCT + SVD 把水印藏进频域，截图、裁剪、旋转后依然可恢复，设计非常优雅。
