# PyInstaller spec for a console-free Windows GUI executable.
# Build locally: pip install pyinstaller && pyinstaller chronobright.spec
# dist/ChronoBright.exe is the user-facing artifact (no Python required).
# pylint: disable=undefined-variable
block_cipher = None

a = Analysis(
    ["chronobright/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["customtkinter", "screen_brightness_control", "pystray", "PIL"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    name="ChronoBright",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
