# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

datas = [
    ('.env.example', '.'),
    ('automate_icon.ico', '.'),
]
binaries = []
hiddenimports = [
    'automate',
    'automate.cli',
    'automate.ui',
    'automate.agent',
    'automate.config',
    'automate.logger',
    'automate.actions',
    'automate.human_input',
    'automate.input_controller',
    'automate.keep_awake',
    'automate.recipes',
    'automate.screen',
    'automate.tools',
    'automate.continuous',
    'automate.providers.cloudflare',
    'automate.providers.anthropic',
    'PIL',
    'PIL._tkinter_finder',
    'pydantic',
    'pydantic_settings',
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'pywinauto',
    'pyautogui',
    'requests',
    'click',
    'rich',
]

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
datas += ctk_datas
binaries += ctk_binaries
hiddenimports += ctk_hiddenimports

auto_datas, auto_binaries, auto_hiddenimports = collect_all('automate')
datas += auto_datas
binaries += auto_binaries
hiddenimports += auto_hiddenimports

a = Analysis(
    ['main_gui.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoMate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='automate_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AutoMate',
)
