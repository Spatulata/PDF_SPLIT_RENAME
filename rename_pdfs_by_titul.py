#!/usr/bin/env python3
"""
Переименовывает PDF-комплекты в папке по данным с титульного листа.

Формат имени: «1360.443291.2002 Поддон шасси ВЧ-генератора.pdf»

Ожидает папку с файлами вроде 1.pdf, 2.pdf, ... (после split_pdf_by_titul).
Читает только первую страницу каждого PDF.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image


# Зоны шапки титульника: номер (центр) и название (строка под номерами)
HEADER_REGION = (0.0, 0.05, 1.0, 0.32)
NUMBER_REGION = (0.20, 0.05, 0.78, 0.20)
TITLE_REGION = (0.05, 0.12, 0.90, 0.28)

# Основной обозначения ЕСКД: 1360.443291.2002
DOC_NUMBER_RE = re.compile(r"\b\d{4}\.\d{5,}\.\d{2,}(?:\.\d+)?\b")
# Альтернатива (организация/УД): 02069102.01200.00697 — не используем для имени
ALT_NUMBER_RE = re.compile(r"\b\d{8}\.\d{5}\.\d{5}\b")

SKIP_TITLE_LINES = {
    "КОМПЛЕКТ ДОКУМЕНТОВ",
    "КОМПЛЕКТ ДОКУМЕНТА",
    "НА ТЕХНОЛОГИЧЕСКИЙ ПРОЦЕСС",
    "ТЕХНОЛОГИЧЕСКИЙ ПРОЦЕСС",
    "УТВЕРЖДАЮ",
    "ТИТУЛЬНЫЙ ЛИСТ",
    "ТЛ",
    "ИЗМ",
    "ЛИСТ",
    "ПОДП",
    "ДАТА",
    "№ ДОКУМ",
    "ДУБЛ",
    "ВЗАМ",
}

OCR_EQUIV = str.maketrans(
    {
        "0": "О",
        "O": "О",
        "Q": "О",
        "1": "I",
        "L": "I",
        "|": "I",
        "!": "I",
        "3": "З",
        "4": "Ч",
        "6": "Б",
        "8": "В",
        "«": "",
        "»": "",
        "„": "",
        "“": "",
        "”": "",
    }
)


@dataclass
class DocMeta:
    number: str | None
    title: str | None
    raw_header: str = ""


_TESSDATA_DIR: Path | None = None
_TESSERACT_CONFIG: str = ""


def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # source next to split script; portable package may copy both
    return Path(__file__).resolve().parent


def get_tessdata_dir() -> Path | None:
    return _TESSDATA_DIR


def tessdata_config(extra: str = "") -> str:
    cfg = _TESSERACT_CONFIG
    if extra:
        return f"{cfg} {extra}".strip()
    return cfg


def _tesseract_exe_candidates() -> list[Path]:
    bundle = get_bundle_dir()
    return [
        bundle / "tesseract" / "tesseract.exe",
        # If launched from scan_split package layout
        bundle.parent / "tesseract" / "tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]


def _resolve_tessdata_dir(exe: Path) -> Path | None:
    candidates = [
        get_bundle_dir() / "tesseract" / "tessdata",
        get_bundle_dir().parent / "tesseract" / "tessdata",
        exe.parent / "tessdata",
    ]
    for tessdata in candidates:
        if tessdata.is_dir() and any(tessdata.glob("*.traineddata")):
            return tessdata
    return None


def configure_tesseract() -> bool:
    global _TESSDATA_DIR, _TESSERACT_CONFIG

    if sys.platform == "win32":
        for exe in _tesseract_exe_candidates():
            if not exe.is_file():
                continue
            tessdata = _resolve_tessdata_dir(exe)
            if tessdata is None:
                continue
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            os.environ["TESSDATA_PREFIX"] = str(tessdata.parent) + os.sep
            _TESSDATA_DIR = tessdata
            _TESSERACT_CONFIG = f'--tessdata-dir "{tessdata}"'
            return True

    try:
        pytesseract.get_tesseract_version()
        for exe in _tesseract_exe_candidates():
            if exe.is_file():
                tessdata = _resolve_tessdata_dir(exe)
                if tessdata is not None:
                    _TESSDATA_DIR = tessdata
                    _TESSERACT_CONFIG = f'--tessdata-dir "{tessdata}"'
                    os.environ["TESSDATA_PREFIX"] = str(tessdata.parent) + os.sep
                    break
        return True
    except pytesseract.TesseractNotFoundError:
        return False


def list_installed_tesseract_langs() -> list[str]:
    try:
        return sorted(pytesseract.get_languages(config=tessdata_config()))
    except pytesseract.TesseractError:
        tessdata = get_tessdata_dir()
        if tessdata is None or not tessdata.is_dir():
            return []
        return sorted(path.stem for path in tessdata.glob("*.traineddata"))


def validate_tesseract_lang(lang: str) -> tuple[bool, list[str]]:
    installed = set(list_installed_tesseract_langs())
    missing: list[str] = []
    for part in lang.split("+"):
        part = part.strip()
        if part and part not in installed:
            missing.append(part)
    return len(missing) == 0, missing


def tesseract_install_hint() -> str:
    if sys.platform == "win32":
        return (
            "Tesseract OCR не найден.\n"
            "Положите portable Tesseract рядом с exe:\n"
            "  tesseract\\tesseract.exe\n"
            "  tesseract\\tessdata\\rus.traineddata\n"
            "Или установите: https://github.com/UB-Mannheim/tesseract/wiki"
        )
    return (
        "Tesseract OCR не установлен.\n"
        "macOS: brew install tesseract tesseract-lang\n"
        "Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-rus"
    )


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("Ё", "Е").replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.upper().strip()


def normalize_ocr(text: str) -> str:
    return normalize_text(text.translate(OCR_EQUIV))


def sanitize_filename(name: str, max_len: int = 140) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "document"
    return name[:max_len]


def render_page(page: fitz.Page, dpi: int) -> Image.Image:
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def pil_to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def cv_to_pil(image: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def rotate_bound(image: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.05:
        return image
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(height * sin + width * cos)
    new_h = int(height * cos + width * sin)
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(
        image,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def detect_skew_angle(gray: np.ndarray, max_angle: float = 12.0) -> float:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    morphed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    coords = np.column_stack(np.where(morphed > 0))
    if len(coords) < 500:
        coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 500:
        return 0.0

    rect = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle
    if abs(angle) > max_angle:
        return 0.0
    return float(angle)


def deskew_image(image: Image.Image, max_angle: float = 12.0) -> Image.Image:
    cv_img = pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    angle = detect_skew_angle(gray, max_angle=max_angle)
    if abs(angle) < 0.2:
        return image
    return cv_to_pil(rotate_bound(cv_img, angle))


def crop_fraction(image: Image.Image, region: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left = int(width * region[0])
    top = int(height * region[1])
    right = int(width * region[2])
    bottom = int(height * region[3])
    return image.crop((left, top, right, bottom))


def ocr_image(image: Image.Image, lang: str, psm: int = 6) -> str:
    return pytesseract.image_to_string(
        image,
        lang=lang,
        config=tessdata_config(f"--psm {psm}"),
    )


def enhance_for_ocr(image: Image.Image) -> Image.Image:
    """Лёгкая бинаризация — лучше читает шапку рамки на серых сканах."""
    cv_img = pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # upscale small crops
    h, w = gray.shape
    if w < 1200:
        scale = 1200 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(binary)


def extract_doc_number(text: str) -> str | None:
    """Берём обозначение вида 1360.443291.2002, не путая с 02069102.01200.00697."""
    candidates: list[str] = []
    for match in DOC_NUMBER_RE.finditer(text):
        value = match.group(0).strip()
        # отсекаем куски, похожие на дату/изм., и 8-значные организационные
        if ALT_NUMBER_RE.fullmatch(value):
            continue
        left, mid, right = value.split(".", 2)[0], value.split(".", 2)[1], value.split(".", 2)[2]
        if len(left) != 4:
            continue
        if not (5 <= len(mid) <= 8):
            continue
        candidates.append(value)

    if not candidates:
        return None

    # Предпочитаем типичную длину середины 6 цифр (443291)
    preferred = [c for c in candidates if len(c.split(".")[1]) == 6]
    return (preferred or candidates)[0]


def _is_org_line(norm: str) -> bool:
    org_tokens = ("ПИ ", "ДГТУ", "ФИЛИАЛ", "ТАГАНРОГ", "УНИВЕРСИТЕТ", "ИНСТИТУТ")
    return any(token in norm for token in org_tokens)


def _is_skip_title(norm: str) -> bool:
    if norm in SKIP_TITLE_LINES:
        return True
    if any(norm.startswith(s) for s in SKIP_TITLE_LINES if len(s) >= 4):
        return True
    if "КОМПЛЕКТ" in norm and "ДОКУМЕНТ" in norm:
        return True
    if "ТЕХНОЛОГИЧ" in norm and "ПРОЦЕСС" in norm:
        return True
    if "ТИТУЛЬН" in norm and "ЛИСТ" in norm:
        return True
    return False


def extract_doc_title(text: str) -> str | None:
    """Название изделия — обычно короткая строка под обозначением в шапке."""
    lines = [raw.strip() for raw in text.splitlines() if raw.strip()]
    scored: list[tuple[int, str]] = []

    for line in lines:
        # OCR часто склеивает название с «01» из соседней ячейки
        line = re.sub(r"\s+\d{1,3}$", "", line).strip()
        if len(line) < 4 or len(line) > 80:
            continue
        norm = normalize_ocr(line)
        if _is_skip_title(norm) or _is_org_line(norm):
            continue
        if DOC_NUMBER_RE.search(line) or ALT_NUMBER_RE.search(line):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if not re.search(r"[А-Яа-яA-Za-z]", line):
            continue
        # типичные ложные срабатывания из блока изменений
        if re.fullmatch(r"[А-ЯA-Z]{1,3}\.?\d{0,3}[-–]?\d{0,4}", line.replace(" ", "")):
            continue

        score = 0
        # кириллица — хороший признак названия
        cyr = len(re.findall(r"[А-Яа-яЁё]", line))
        score += min(cyr, 20)
        # разумная длина названия изделия
        if 8 <= len(line) <= 55:
            score += 8
        elif 4 <= len(line) <= 70:
            score += 3
        # дефис/знак «ВЧ-» и т.п. часто в названиях
        if "-" in line or "–" in line:
            score += 2
        scored.append((score, line))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_line = scored[0]
    if best_score < 6:
        return None
    return best_line.strip()


def read_first_page_meta(pdf_path: Path, dpi: int, lang: str, deskew: bool) -> DocMeta:
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            return DocMeta(None, None)
        page = doc[0]

        embedded = page.get_text("text")
        if len(embedded.strip()) >= 40 and extract_doc_number(embedded):
            number = extract_doc_number(embedded)
            title = extract_doc_title(embedded)
            if number and title:
                return DocMeta(number, title, embedded)

        image = render_page(page, dpi=dpi)
        if deskew:
            image = deskew_image(image)

        header = crop_fraction(image, HEADER_REGION)
        number_crop = crop_fraction(image, NUMBER_REGION)
        title_crop = crop_fraction(image, TITLE_REGION)

        chunks = [
            ocr_image(enhance_for_ocr(header), lang=lang, psm=6),
            ocr_image(enhance_for_ocr(number_crop), lang=lang, psm=7),
            ocr_image(enhance_for_ocr(title_crop), lang=lang, psm=6),
        ]
        if embedded.strip():
            chunks.append(embedded)

        combined = "\n".join(chunks)
        return DocMeta(
            number=extract_doc_number(combined),
            title=extract_doc_title(combined),
            raw_header=combined,
        )


def build_new_name(meta: DocMeta, fallback_stem: str) -> str:
    if meta.number and meta.title:
        return sanitize_filename(f"{meta.number} {meta.title}") + ".pdf"
    if meta.number:
        return sanitize_filename(meta.number) + ".pdf"
    if meta.title:
        return sanitize_filename(f"{fallback_stem} {meta.title}") + ".pdf"
    return sanitize_filename(fallback_stem) + ".pdf"


def unique_path(directory: Path, filename: str, reserved: set[str]) -> Path:
    base = Path(filename)
    stem, suffix = base.stem, base.suffix
    candidate = directory / filename
    n = 2
    while candidate.name.lower() in reserved or candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def pdf_sort_key(path: Path) -> tuple:
    stem = path.stem
    if stem.isdigit():
        return (0, int(stem), stem.lower())
    match = re.match(r"^(\d+)", stem)
    if match:
        return (0, int(match.group(1)), stem.lower())
    return (1, 0, stem.lower())


def collect_pdfs(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=pdf_sort_key,
    )


def rename_folder(
    folder: Path,
    dpi: int,
    lang: str,
    deskew: bool,
    dry_run: bool,
) -> tuple[int, int]:
    pdfs = collect_pdfs(folder)
    if not pdfs:
        print(f"В папке нет PDF: {folder}")
        return 0, 0

    print(f"Найдено PDF: {len(pdfs)}")
    renamed = 0
    skipped = 0

    # Двухпроходное переименование: сначала во временные имена, чтобы не затереть.
    plan: list[tuple[Path, Path, DocMeta]] = []
    reserved: set[str] = set()

    for pdf in pdfs:
        print(f"\nOCR: {pdf.name} ...")
        meta = read_first_page_meta(pdf, dpi=dpi, lang=lang, deskew=deskew)
        new_name = build_new_name(meta, fallback_stem=pdf.stem)

        if meta.number or meta.title:
            print(f"  номер: {meta.number or '—'}")
            print(f"  название: {meta.title or '—'}")
        else:
            print("  [!] номер/название не распознаны — имя оставим близким к исходному")

        if new_name.lower() == pdf.name.lower():
            print(f"  без изменений: {pdf.name}")
            reserved.add(pdf.name.lower())
            skipped += 1
            continue

        target = unique_path(folder, new_name, reserved)
        reserved.add(target.name.lower())
        plan.append((pdf, target, meta))

    if dry_run:
        print("\n--- dry-run ---")
        for src, dst, _ in plan:
            print(f"  {src.name}  ->  {dst.name}")
        print(f"Будет переименовано: {len(plan)}, без изменений: {skipped}")
        return len(plan), skipped

    # 1) во временные имена
    temps: list[tuple[Path, Path]] = []
    for i, (src, dst, _) in enumerate(plan, start=1):
        tmp = folder / f".__rename_tmp_{i:04d}__.pdf"
        if tmp.exists():
            tmp.unlink()
        src.rename(tmp)
        temps.append((tmp, dst))

    # 2) во финальные
    for tmp, dst in temps:
        if dst.exists():
            dst = unique_path(folder, dst.name, set())
        tmp.rename(dst)
        print(f"  -> {dst.name}")
        renamed += 1

    return renamed, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Переименовать PDF в папке по номеру и названию с титульного листа. "
            "Формат: «1360.443291.2002 Поддон шасси ВЧ-генератора.pdf»"
        )
    )
    parser.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=None,
        help="Папка с PDF (после разбиения: 1.pdf, 2.pdf, ...)",
    )
    parser.add_argument("--dpi", type=int, default=220, help="DPI для OCR (по умолчанию: 220)")
    parser.add_argument("--lang", default="rus", help="Язык Tesseract (по умолчанию: rus)")
    parser.add_argument(
        "--no-deskew",
        action="store_true",
        help="Не выравнивать наклон первой страницы",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать новые имена, не переименовывать",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.folder is None:
        print(
            "Укажите папку с PDF или перетащите её на run_rename.bat\n"
            "Пример: rename_pdfs_by_titul.exe \"C:\\path\\to\\scan_split\""
        )
        return 1

    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"Папка не найдена: {folder}", file=sys.stderr)
        return 1

    try:
        if not configure_tesseract():
            raise pytesseract.TesseractNotFoundError()
    except pytesseract.TesseractNotFoundError:
        print(tesseract_install_hint(), file=sys.stderr)
        return 1

    lang_ok, missing = validate_tesseract_lang(args.lang)
    if not lang_ok:
        print(
            f"Нет языкового пакета Tesseract: {', '.join(missing)}\n"
            f"Нужен файл tessdata\\{missing[0]}.traineddata",
            file=sys.stderr,
        )
        return 1

    print(f"Папка: {folder}")
    print(f"OCR: dpi={args.dpi}, lang={args.lang}, deskew={'нет' if args.no_deskew else 'да'}")
    if args.dry_run:
        print("Режим: dry-run (без переименования)")

    renamed, skipped = rename_folder(
        folder=folder,
        dpi=args.dpi,
        lang=args.lang,
        deskew=not args.no_deskew,
        dry_run=args.dry_run,
    )

    print(f"\nГотово. Переименовано: {renamed}, без изменений: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
