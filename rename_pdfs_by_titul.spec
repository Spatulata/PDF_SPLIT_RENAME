# -*- mode: python ; coding: utf-8 -*-
# Сборка: build_windows.bat (на Windows)

block_cipher = None

# PDF/OCR нужны только базовые форматы PNG/JPEG — AVIF/WebP/HEIF ломают PyInstaller на Windows.
PIL_SKIP_MODULES = (
    "PIL._avif",
    "PIL._heif",
    "PIL._webp",
    "PIL._imagingtk",
)


def _drop_optional_pil_binaries(binaries):
    out = []
    for name, path, typecode in binaries:
        low = name.replace("\\", "/").lower()
        if any(skip.lower().replace(".", "/") in low for skip in PIL_SKIP_MODULES):
            continue
        if any(tag in low for tag in ("_avif.", "_heif.", "_webp.", "_imagingtk.")):
            continue
        out.append((name, path, typecode))
    return out


a = Analysis(
    ["rename_pdfs_by_titul.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "cv2",
        "numpy",
        "fitz",
        "PIL",
        "PIL.Image",
        "pytesseract",
        "tesseract_paths",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        *PIL_SKIP_MODULES,
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = _drop_optional_pil_binaries(a.binaries)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="rename_pdfs_by_titul",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
