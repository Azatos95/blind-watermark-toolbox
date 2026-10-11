# 盲水印工具箱 —— 一键构建单文件 exe
# 用法:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1
#
# 依赖算法核心 guofei9987/blind_watermark (MIT, Copyright (c) 2019 郭飞)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$venv = Join-Path $root '.venv-build'

Write-Host "==> 项目根目录: $root" -ForegroundColor Cyan

# 1) 虚拟环境(复用本机已安装的 numpy/opencv, 避免重复下载几百 MB)
if (-not (Test-Path $venv)) {
    Write-Host "==> 创建虚拟环境(--system-site-packages)..." -ForegroundColor Cyan
    python -m venv --system-site-packages $venv
}
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { throw "找不到虚拟环境 python: $py" }

# 2) 安装依赖
Write-Host "==> 安装依赖 (blind-watermark / pyinstaller / tkinterdnd2)..." -ForegroundColor Cyan
& $py -m pip install --no-input --upgrade pip
& $py -m pip install --no-input blind-watermark==0.4.4 pyinstaller tkinterdnd2

# 3) 打包
Write-Host "==> PyInstaller 打包..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean bwm_gui.spec

$exe = Join-Path $root 'dist\盲水印工具箱.exe'
if (-not (Test-Path $exe)) { throw "打包失败, 未生成 $exe" }
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "==> 产物: $exe  ($mb MB)" -ForegroundColor Green

# 4) 自检(验证打包产物在目标机上真的能跑)
Write-Host "==> 运行内置自检 --selftest ..." -ForegroundColor Cyan
& $exe --selftest
Write-Host "==> 完成。自检报告见 exe 同目录的 selftest_report.txt" -ForegroundColor Green
