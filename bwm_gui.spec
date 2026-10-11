# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - 盲水印工具箱

构建:  .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean bwm_gui.spec
产物:  dist\盲水印工具箱.exe   (单文件, 免安装, 双击即用)
"""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# tkinterdnd2 的 tkdnd 是运行时由 Tcl 从磁盘加载的扩展, 必须原样随包分发
try:
    dnd_datas = collect_data_files('tkinterdnd2')
except Exception:
    dnd_datas = []

a = Analysis(
    ['bwm_gui.py'],
    pathex=[],
    binaries=[],
    datas=dnd_datas,
    hiddenimports=[
        'blind_watermark',
        'blind_watermark.bwm_core',
        'blind_watermark.cli_tools',
        'blind_watermark.att',
        'blind_watermark.recover',
        'blind_watermark.pool',
        'pywt',
        'pywt._extensions._cwt',
        'cv2',
        'numpy',
        'tkinterdnd2',
        'tkinterdnd2.TkinterDnD',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除体积大户: 用不到的 GUI/科学计算/matplotlib 等
    excludes=[
        'matplotlib', 'scipy', 'pandas', 'PIL', 'IPython', 'jupyter',
        'pytest', 'setuptools', 'pip', 'wheel', 'sqlite3', 'test',
        'unittest', 'pydoc', 'lib2to3', 'tornado', 'zmq', 'notebook',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='盲水印工具箱',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX 压缩容易被杀软误报, 关闭
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # GUI 程序: 不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # 有图标时填 'app.ico'
)
