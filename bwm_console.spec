# -*- mode: python ; coding: utf-8 -*-
"""诊断版: 同样内容但保留控制台, 用于查看打包后 exe 的实时输出/报错"""

HIDDEN = [
    'blind_watermark', 'blind_watermark.bwm_core', 'blind_watermark.cli_tools',
    'blind_watermark.att', 'blind_watermark.recover', 'blind_watermark.pool',
    'pywt', 'pywt._extensions._cwt', 'cv2', 'numpy',
]
EXCLUDES = [
    'matplotlib', 'scipy', 'pandas', 'PIL', 'IPython', 'jupyter',
    'pytest', 'setuptools', 'pip', 'wheel', 'sqlite3', 'test',
    'unittest', 'pydoc', 'lib2to3', 'tornado', 'zmq', 'notebook',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
]

a = Analysis(
    ['bwm_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='bwm_console',
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
    runtime_tmpdir=r'C:\Users\A\AppData\Local\Temp',
)
