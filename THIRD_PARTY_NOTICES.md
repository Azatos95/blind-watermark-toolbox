# 第三方依赖与开源协议声明

本项目的图形界面与打包工程为本仓库原创（MIT），但运行所依赖的组件版权归各自作者所有。

## 核心算法（本项目的前提）

| 组件 | 版本 | 协议 | 作者 / 来源 |
|---|---|---|---|
| **blind-watermark** | 0.4.4 | **MIT** | **郭飞 (guofei9987)** — https://github.com/guofei9987/blind_watermark |

> ⚠️ 盲水印的算法思想与实现**完全来自 blind-watermark**。原项目版权声明：
> `MIT License, Copyright (c) 2019 郭飞`。
> 本仓库不含任何算法层面的原创贡献，仅提供 GUI 与打包。

## 运行时依赖

| 组件 | 版本 | 协议 | 来源 |
|---|---|---|---|
| NumPy | 2.4.6 | BSD-3-Clause | https://numpy.org |
| OpenCV (opencv-python) | 4.13.0 | Apache-2.0 | https://opencv.org |
| PyWavelets | 1.8.0 / 1.9.0 | MIT | https://github.com/PyWavelets/pywavelets |
| tkinterdnd2 | 0.6.3 | MIT | https://github.com/pmgagne/tkinterdnd2 |
| TkDND (tkdnd) | 2.10.2 | Tcl/Tk 风格许可 | https://github.com/petasis/tkdnd |
| Tcl/Tk (tkinter 运行时) | 随 Python 3.14 | BSD 风格 | https://www.tcl.tk |
| Python | 3.14.2 | PSF-2.0 | https://www.python.org |

## 打包工具

| 组件 | 版本 | 协议 |
|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0-or-later **附例外条款**（打包产物不受 GPL 约束，可自由分发） |
| pyinstaller-hooks-contrib | 2026.8 | Apache-2.0 |
| pefile | 2024.8.26 | MIT |
| altgraph | 0.17.5 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |

## 使用与再分发注意

- 本仓库以 **MIT** 发布：可自由使用、修改、商用，但**必须保留原作者的版权声明**
  （即 `LICENSE` 中的 `Copyright (c) 2019 郭飞`）。
- 用 PyInstaller 打包出的 exe 内含上述各库，**分发时请随附本文件与 LICENSE**。
- OpenCV 为 Apache-2.0，可商用；NumPy 为 BSD-3-Clause，可商用。
- 若用于法律取证、版权确权等场景，请自行评估算法鲁棒性边界（见 README「必须知道的算法约束」），
  并建议引用原项目作者的说明。
