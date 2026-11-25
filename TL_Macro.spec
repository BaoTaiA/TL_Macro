# -*- mode: python ; coding: utf-8 -*-
"""TL_Macro v1.6.3 PyInstaller spec - onedir 分离打包，含 GDI/DXGI 双截屏后端"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

project_root = SPECPATH

datas = [
    (os.path.join(project_root, 'resources', 'tl.ico'), 'resource'),
]
datas += collect_data_files('webview')

binaries = []
try:
    binaries += collect_dynamic_libs('pythonnet')
except Exception:
    pass

hiddenimports = [
    # 应用模块（截屏后端 lazy import 兜底）
    'global_settings',
    'global_settings_tab',
    'process_history',
    'screen_capture',
    # 图像 / 数值
    'cv2',
    'numpy',
    'numpy._core._multiarray_umath',
    # GDI 截屏
    'mss',
    'mss.windows',
    # DXGI 截屏（bettercam 延迟 import，需显式收集子模块）
    'bettercam',
    'bettercam.processor.numpy_processor',
    'bettercam.core.duplicator',
    'bettercam.core.device',
    'bettercam.core.output',
    'bettercam.core.stagesurf',
    'bettercam._libs.dxgi',
    'bettercam._libs.d3d11',
    'bettercam._libs.user32',
    # comtypes（bettercam DXGI 绑定）
    'comtypes',
    'comtypes.client',
    'comtypes.persist',
    'comtypes.typeinfo',
    'comtypes.automation',
    'comtypes.stream',
    'ctypes.wintypes',
    # 热键 / 输入
    'keyboard',
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'pynput.keyboard._win32',
    'pynput.mouse._win32',
    # WebView 关于页
    'webview',
    'webview.platforms',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'clr_loader',
    'pythonnet',
    'PyQt5.sip',
]
hiddenimports += collect_submodules('bettercam')

excludes = [
    'PIL',
    'Pillow',
    'pyautogui',
    'pyscreeze',
    'mouseinfo',
    'matplotlib',
    'scipy',
    'pandas',
    'jupyter',
    'IPython',
    'pytest',
    'unittest',
    'test',
    'tests',
    'comtypes.test',
    'debugpy',
    'tkinter',
    'turtle',
    'lib2to3',
    'pydoc',
    'doctest',
    'xmlrpc',
    'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtQml',
    'PyQt5.QtQuick',
    'PyQt5.QtBluetooth',
    'PyQt5.QtMultimedia',
]

a = Analysis(
    [os.path.join(project_root, 'app.py')],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TL_Macro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    uac_admin=True,
    icon=os.path.join(project_root, 'resources', 'tl.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TL_Macro',
)
