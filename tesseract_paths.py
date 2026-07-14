"""Поиск portable/system Tesseract и tessdata на Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytesseract

_TESSDATA_DIR: Path | None = None
_TESSERACT_EXE: Path | None = None
_TESSERACT_CONFIG: str = ""


def get_bundle_dir(caller_file: str | Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(caller_file).resolve().parent


def get_tessdata_dir() -> Path | None:
    return _TESSDATA_DIR


def get_tesseract_exe() -> Path | None:
    return _TESSERACT_EXE


def tessdata_config(extra: str = "") -> str:
    parts = []
    if _TESSERACT_CONFIG:
        parts.append(_TESSERACT_CONFIG)
    if extra:
        parts.append(extra.strip())
    return " ".join(parts)


def _langs_on_disk(tessdata: Path) -> set[str]:
    if not tessdata.is_dir():
        return set()
    return {path.stem for path in tessdata.glob("*.traineddata")}


def _matched_tesseract_pairs(bundle: Path) -> list[tuple[Path, Path, int]]:
    """Только согласованные пары exe + tessdata (не смешиваем portable и Program Files)."""
    pairs: list[tuple[Path, Path, int]] = []

    portable_exe = bundle / "tesseract" / "tesseract.exe"
    portable_tess = bundle / "tesseract" / "tessdata"
    if portable_exe.is_file() and portable_tess.is_dir():
        pairs.append((portable_exe, portable_tess, 100))

    for exe in (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ):
        tessdata = exe.parent / "tessdata"
        if exe.is_file() and tessdata.is_dir():
            pairs.append((exe, tessdata, 50))

    return pairs


def _apply_tesseract_paths(exe: Path, tessdata: Path, extra_config: str = "") -> None:
    global _TESSDATA_DIR, _TESSERACT_CONFIG, _TESSERACT_EXE

    exe = exe.resolve()
    tessdata = tessdata.resolve()
    prefix = tessdata.parent

    pytesseract.pytesseract.tesseract_cmd = str(exe)
    os.environ["TESSDATA_PREFIX"] = str(prefix)
    _TESSERACT_EXE = exe
    _TESSDATA_DIR = tessdata
    _TESSERACT_CONFIG = extra_config.strip()


def _path_apply_variants(exe: Path, tessdata: Path) -> list[tuple[str, str]]:
    """Разные способы указать tessdata — portable Tesseract на Windows капризный."""
    exe = exe.resolve()
    tessdata = tessdata.resolve()
    prefix = tessdata.parent
    td_posix = tessdata.as_posix()

    return [
        ("prefix", ""),
        ("prefix_slash", ""),
        ("tessdata_dir_posix", f"--tessdata-dir {td_posix}"),
        ("tessdata_dir_native", f"--tessdata-dir {tessdata}"),
    ]


def _probe_pair(exe: Path, tessdata: Path, required: list[str]) -> set[str] | None:
    """Пробует пару exe+tessdata; возвращает загруженные языки или None."""
    on_disk = _langs_on_disk(tessdata)
    if not on_disk:
        return None
    if required and not all(lang in on_disk for lang in required):
        return None

    for _name, extra_config in _path_apply_variants(exe, tessdata):
        prefix = tessdata.parent.resolve()
        _apply_tesseract_paths(exe, tessdata, extra_config)

        # Варианты TESSDATA_PREFIX
        for prefix_value in (str(prefix), str(prefix) + os.sep):
            os.environ["TESSDATA_PREFIX"] = prefix_value
            try:
                loaded = set(pytesseract.get_languages(config=tessdata_config()))
            except pytesseract.TesseractError:
                continue
            if loaded and all(lang in loaded for lang in required):
                return loaded

    return None


def find_working_tesseract_pair(
    bundle: Path,
    required_langs: list[str] | None = None,
) -> tuple[Path, Path, set[str]] | None:
    required = required_langs or ["rus"]

    for exe, tessdata, _priority in _matched_tesseract_pairs(bundle):
        loaded = _probe_pair(exe, tessdata, required)
        if loaded is not None:
            return exe, tessdata, loaded

    return None


def configure_tesseract(bundle: Path, required_langs: list[str] | None = None) -> bool:
    global _TESSDATA_DIR, _TESSERACT_CONFIG, _TESSERACT_EXE

    required = required_langs or ["rus"]
    found = find_working_tesseract_pair(bundle, required)
    if found is not None:
        exe, tessdata, _loaded = found
        # Пути уже применены в _probe_pair; повторно пробуем финальную конфигурацию
        _probe_pair(exe, tessdata, required)
        return True

    _TESSDATA_DIR = None
    _TESSERACT_EXE = None
    _TESSERACT_CONFIG = ""

    if sys.platform != "win32":
        try:
            pytesseract.get_tesseract_version()
            return True
        except pytesseract.TesseractNotFoundError:
            return False

    return False


def list_installed_tesseract_langs() -> list[str]:
    try:
        loaded = sorted(pytesseract.get_languages(config=tessdata_config()))
        if loaded:
            return loaded
    except pytesseract.TesseractError:
        pass

    tessdata = get_tessdata_dir()
    if tessdata and tessdata.is_dir():
        return sorted(_langs_on_disk(tessdata))
    return []


def validate_tesseract_lang(lang: str) -> tuple[bool, list[str]]:
    installed = set(list_installed_tesseract_langs())
    missing = [part.strip() for part in lang.split("+") if part.strip() and part.strip() not in installed]
    return len(missing) == 0, missing


def verify_tesseract_runtime(lang: str) -> None:
    tessdata = get_tessdata_dir()
    exe = get_tesseract_exe()
    if tessdata is None or exe is None:
        raise RuntimeError(
            "Tesseract/tessdata не найдены.\n"
            "Установите Tesseract: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "Или положите portable tesseract\\ рядом с exe."
        )

    for part in lang.split("+"):
        part = part.strip()
        if not part:
            continue
        lang_file = tessdata / f"{part}.traineddata"
        if not lang_file.is_file():
            raise RuntimeError(
                f"Нет языкового файла: {lang_file}\n"
                "Запустите install_tesseract_rus.bat"
            )

    try:
        loaded = set(pytesseract.get_languages(config=tessdata_config()))
    except pytesseract.TesseractError as exc:
        prefix = os.environ.get("TESSDATA_PREFIX", "")
        raise RuntimeError(
            "Tesseract не смог загрузить языки.\n"
            f"  exe: {exe}\n"
            f"  tessdata: {tessdata}\n"
            f"  TESSDATA_PREFIX: {prefix}\n"
            f"  config: {tessdata_config() or '(empty)'}\n"
            f"  {exc}"
        ) from exc

    missing = [part for part in lang.split("+") if part.strip() and part.strip() not in loaded]
    if missing:
        on_disk = ", ".join(sorted(_langs_on_disk(tessdata))) or "нет файлов"
        raise RuntimeError(
            f"Языки не загружены: {', '.join(missing)}\n"
            f"  exe: {exe}\n"
            f"  tessdata: {tessdata}\n"
            f"  файлы на диске: {on_disk}\n"
            f"  загружено Tesseract: {', '.join(sorted(loaded)) or 'ничего'}\n\n"
            "Portable tesseract\\ не работает — установите Tesseract в Program Files\n"
            "или пересоберите папку tesseract\\ целиком из рабочего portable-бандла."
        )


def describe_tesseract_setup() -> str:
    exe = get_tesseract_exe()
    tessdata = get_tessdata_dir()
    if exe and tessdata:
        return f"Tesseract: {exe}\nTesseract tessdata: {tessdata}"
    return ""


def tesseract_install_hint() -> str:
    if sys.platform == "win32":
        return (
            "Tesseract OCR не найден или не загружает rus.\n"
            "Вариант 1 (рекомендуется): установите Tesseract:\n"
            "  https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  при установке отметьте Russian language\n"
            "Вариант 2: install_tesseract_rus.bat скопирует rus в tesseract\\tessdata\\\n"
            "Вариант 3: portable tesseract\\ — exe + tessdata + все DLL из одного комплекта"
        )
    return (
        "Tesseract OCR не установлен.\n"
        "macOS: brew install tesseract tesseract-lang\n"
        "Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-rus"
    )


def tesseract_lang_hint(lang: str, missing: list[str]) -> str:
    tessdata = get_tessdata_dir()
    exe = get_tesseract_exe()
    tessdata_hint = str(tessdata) if tessdata else r"tesseract\tessdata"
    exe_hint = str(exe) if exe else "не найден"
    on_disk = ", ".join(sorted(_langs_on_disk(tessdata))) if tessdata else "не найдены"
    missing_hint = ", ".join(missing)
    return (
        f"Языковой пакет Tesseract не найден: {missing_hint}\n"
        f"exe: {exe_hint}\n"
        f"Папка tessdata: {tessdata_hint}\n"
        f"Файлы на диске: {on_disk}\n\n"
        "Как исправить на Windows:\n"
        "  1) Установите Tesseract с Russian language (Program Files)\n"
        "  2) install_tesseract_rus.bat — скопирует rus в portable tessdata\\\n"
        "  3) Пересоберите exe: build_windows.bat"
    )
