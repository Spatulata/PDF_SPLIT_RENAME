"""Поиск portable/system Tesseract и tessdata на Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytesseract

_TESSDATA_DIR: Path | None = None
_TESSERACT_CONFIG: str = ""


def get_bundle_dir(caller_file: str | Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(caller_file).resolve().parent


def get_tessdata_dir() -> Path | None:
    return _TESSDATA_DIR


def tessdata_config(extra: str = "") -> str:
    parts = []
    if _TESSERACT_CONFIG:
        parts.append(_TESSERACT_CONFIG)
    if extra:
        parts.append(extra.strip())
    return " ".join(parts)


def _apply_tesseract_paths(exe: Path, tessdata: Path) -> None:
    global _TESSDATA_DIR, _TESSERACT_CONFIG

    exe = exe.resolve()
    tessdata = tessdata.resolve()
    prefix = tessdata.parent

    pytesseract.pytesseract.tesseract_cmd = str(exe)
    os.environ["TESSDATA_PREFIX"] = str(prefix) + os.sep
    _TESSDATA_DIR = tessdata
    _TESSERACT_CONFIG = ""


def _tesseract_exe_candidates(bundle: Path) -> list[Path]:
    return [
        bundle / "tesseract" / "tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]


def _tessdata_candidates(bundle: Path, exe: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for candidate in (
        bundle / "tesseract" / "tessdata",
        exe.parent / "tessdata",
        Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
    ):
        key = str(candidate.resolve()).lower() if candidate.exists() else str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            out.append(candidate)
    return out


def _langs_on_disk(tessdata: Path) -> set[str]:
    return {path.stem for path in tessdata.glob("*.traineddata")}


def _score_pair(
    exe: Path,
    tessdata: Path,
    bundle: Path,
    required: list[str],
) -> int:
    langs = _langs_on_disk(tessdata)
    if not langs:
        return -1

    score = len(langs)
    score += 20 * sum(1 for lang in required if lang in langs)
    if all(lang in langs for lang in required):
        score += 50

    portable_root = (bundle / "tesseract").resolve()
    if exe.resolve().parent == portable_root:
        score += 10
    if tessdata.resolve() == (portable_root / "tessdata").resolve() and required and all(
        lang in langs for lang in required
    ):
        score += 5

    return score


def find_tesseract_pair(bundle: Path, required_langs: list[str] | None = None) -> tuple[Path, Path] | None:
    required = required_langs or ["rus"]
    best: tuple[int, Path, Path] | None = None

    for exe in _tesseract_exe_candidates(bundle):
        if not exe.is_file():
            continue
        for tessdata in _tessdata_candidates(bundle, exe):
            score = _score_pair(exe, tessdata, bundle, required)
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, exe, tessdata)

    if best is None:
        return None
    return best[1], best[2]


def configure_tesseract(bundle: Path, required_langs: list[str] | None = None) -> bool:
    global _TESSDATA_DIR, _TESSERACT_CONFIG

    required = required_langs or ["rus"]
    pair = find_tesseract_pair(bundle, required)
    if pair is not None:
        exe, tessdata = pair
        _apply_tesseract_paths(exe, tessdata)
        return True

    if sys.platform == "win32":
        return False

    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False


def list_installed_tesseract_langs() -> list[str]:
    tessdata = get_tessdata_dir()
    on_disk = sorted(_langs_on_disk(tessdata)) if tessdata and tessdata.is_dir() else []

    try:
        loaded = sorted(pytesseract.get_languages(config=tessdata_config()))
        if loaded:
            return loaded
    except pytesseract.TesseractError:
        pass

    return on_disk


def validate_tesseract_lang(lang: str) -> tuple[bool, list[str]]:
    installed = set(list_installed_tesseract_langs())
    missing = [part.strip() for part in lang.split("+") if part.strip() and part.strip() not in installed]
    return len(missing) == 0, missing


def verify_tesseract_runtime(lang: str) -> None:
    tessdata = get_tessdata_dir()
    if tessdata is None:
        raise RuntimeError(
            "Tesseract/tessdata не найдены.\n"
            "Нужна папка tesseract\\tessdata\\ с rus.traineddata\n"
            "или установленный Tesseract в Program Files."
        )

    for part in lang.split("+"):
        part = part.strip()
        if not part:
            continue
        lang_file = tessdata / f"{part}.traineddata"
        if not lang_file.is_file():
            raise RuntimeError(
                f"Нет языкового файла: {lang_file}\n"
                "Запустите install_tesseract_rus.bat — он скопирует rus в portable tessdata\\"
            )

    try:
        loaded = set(pytesseract.get_languages(config=tessdata_config()))
    except pytesseract.TesseractError as exc:
        prefix = os.environ.get("TESSDATA_PREFIX", "")
        raise RuntimeError(
            "Tesseract не смог загрузить языки.\n"
            f"  tessdata: {tessdata}\n"
            f"  TESSDATA_PREFIX: {prefix}\n"
            f"  {exc}"
        ) from exc

    missing = [part for part in lang.split("+") if part.strip() and part.strip() not in loaded]
    if missing:
        raise RuntimeError(
            f"Языки не загружены: {', '.join(missing)}\n"
            f"  tessdata: {tessdata}\n"
            f"  доступно: {', '.join(sorted(loaded))}"
        )


def tesseract_install_hint() -> str:
    bundle_hint = "tesseract\\tessdata\\"
    if sys.platform == "win32":
        return (
            "Tesseract OCR не найден.\n"
            "Вариант 1: положите portable Tesseract рядом с exe:\n"
            "  tesseract\\tesseract.exe\n"
            "  tesseract\\tessdata\\rus.traineddata\n"
            "Вариант 2: установите Tesseract и запустите install_tesseract_rus.bat\n"
            "  https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"Вариант 3: install_tesseract_rus.bat скопирует rus в {bundle_hint}"
        )
    return (
        "Tesseract OCR не установлен.\n"
        "macOS: brew install tesseract tesseract-lang\n"
        "Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-rus"
    )


def tesseract_lang_hint(lang: str, missing: list[str]) -> str:
    tessdata = get_tessdata_dir()
    tessdata_hint = str(tessdata) if tessdata else r"tesseract\tessdata"
    installed = list_installed_tesseract_langs()
    installed_hint = ", ".join(installed[:12]) if installed else "не найдены"
    missing_hint = ", ".join(missing)
    return (
        f"Языковой пакет Tesseract не найден: {missing_hint}\n"
        f"Папка tessdata: {tessdata_hint}\n"
        f"Установленные языки: {installed_hint}\n\n"
        "Как исправить на Windows:\n"
        "  1) Запустите install_tesseract_rus.bat — скопирует rus в portable tessdata\\\n"
        "  2) Или вручную скопируйте rus.traineddata в tesseract\\tessdata\\\n"
        "     из C:\\Program Files\\Tesseract-OCR\\tessdata\\\n"
        "  3) Или скачайте:\n"
        "     https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
    )
