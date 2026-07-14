#!/usr/bin/env python3
"""
Разбивает один большой PDF на несколько файлов по титульным листам (ГОСТ/ЕСКД).

Каждый титульник начинает новый комплект: титульник + все страницы до следующего титульника.
Учитывает кривые/смещённые сканы: выравнивание наклона, авто-поворот, нечёткий поиск маркеров.
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


# --- Маркеры титульника ---

STRONG_MARKER_PARTS = (
    ("КОМПЛЕКТ", "ДОКУМЕНТ"),
)

WEAK_MARKER_PARTS = (
    ("ТИТУЛЬН", "ЛИСТ"),
    ("ТЕХНОЛОГИЧ", "ПРОЦЕСС"),
)

WEAK_MARKERS = ("УТВЕРЖДАЮ",)

# Зоны на уже выровненном изображении (доли ширины/высоты) — с запасом по краям
BOTTOM_LEFT_REGION = (0.0, 0.65, 0.55, 1.0)
CENTER_REGION = (0.0, 0.15, 1.0, 0.85)

DOC_NUMBER_RE = re.compile(
    r"\b\d{4}\.\d{6,}\.\d+(?:\.\d+)?(?:\s+[А-ЯA-Z]{1,3})?\b"
)
ALT_NUMBER_RE = re.compile(r"\b\d{8}\.\d{5}\.\d{5}\b")

SKIP_TITLE_LINES = {
    "КОМПЛЕКТ ДОКУМЕНТОВ",
    "КОМПЛЕКТ ДОКУМЕНТА",
    "НА ТЕХНОЛОГИЧЕСКИЙ ПРОЦЕСС",
    "УТВЕРЖДАЮ",
    "ТИТУЛЬНЫЙ ЛИСТ",
    "ТЛ",
    "ИЗМ",
    "ЛИСТ",
    "ПОДП",
    "ДАТА",
    "№ ДОКУМ",
}

# Типичные ошибки OCR для кириллицы/цифр
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
class TitlePageInfo:
    page_index: int
    score: int
    doc_number: str | None
    doc_title: str | None
    skew_angle: float | None = None


_TESSDATA_DIR: Path | None = None
_TESSERACT_CONFIG: str = ""


def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


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
    """Настраивает portable Tesseract рядом с exe."""
    global _TESSDATA_DIR, _TESSERACT_CONFIG

    exe = exe.resolve()
    tessdata = tessdata.resolve()
    prefix = tessdata.parent

    pytesseract.pytesseract.tesseract_cmd = str(exe)
    # TESSDATA_PREFIX = папка tesseract\ (внутри неё лежит tessdata\)
    os.environ["TESSDATA_PREFIX"] = str(prefix) + os.sep
    _TESSDATA_DIR = tessdata
    # Не передаём --tessdata-dir: на Windows кавычки/слэши ломают путь к rus.traineddata
    _TESSERACT_CONFIG = ""


def _tesseract_exe_candidates() -> list[Path]:
    return [
        get_bundle_dir() / "tesseract" / "tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]


def _resolve_tessdata_dir(exe: Path) -> Path | None:
    candidates = [
        get_bundle_dir() / "tesseract" / "tessdata",
        exe.parent / "tessdata",
    ]
    for tessdata in candidates:
        if tessdata.is_dir() and any(tessdata.glob("*.traineddata")):
            return tessdata
    return None


def configure_tesseract() -> bool:
    """Ищет Tesseract и настраивает пути к tessdata."""
    global _TESSDATA_DIR, _TESSERACT_CONFIG

    if sys.platform == "win32":
        for exe in _tesseract_exe_candidates():
            if not exe.is_file():
                continue
            tessdata = _resolve_tessdata_dir(exe)
            if tessdata is None:
                continue
            _apply_tesseract_paths(exe, tessdata)
            return True

    try:
        pytesseract.get_tesseract_version()
        for exe in _tesseract_exe_candidates():
            if exe.is_file():
                tessdata = _resolve_tessdata_dir(exe)
                if tessdata is not None:
                    _apply_tesseract_paths(exe, tessdata)
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
        if not part:
            continue
        if part not in installed:
            missing.append(part)
    return len(missing) == 0, missing


def verify_tesseract_runtime(lang: str) -> None:
    """Проверяет, что Tesseract реально читает языки (не только файлы на диске)."""
    tessdata = get_tessdata_dir()
    if tessdata is None:
        raise RuntimeError("Папка tessdata не найдена рядом с tesseract.exe")

    for part in lang.split("+"):
        part = part.strip()
        if not part:
            continue
        lang_file = tessdata / f"{part}.traineddata"
        if not lang_file.is_file():
            raise RuntimeError(
                f"Нет языкового файла: {lang_file}\n"
                "Запустите install_tesseract_rus.bat или положите rus.traineddata в tessdata\\"
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

    missing = [p for p in lang.split("+") if p.strip() and p.strip() not in loaded]
    if missing:
        raise RuntimeError(
            f"Языки не загружены: {', '.join(missing)}\n"
            f"  tessdata: {tessdata}\n"
            f"  доступно: {', '.join(sorted(loaded))}"
        )


def tesseract_install_hint() -> str:
    if sys.platform == "win32":
        tessdata = get_tessdata_dir()
        tessdata_hint = str(tessdata) if tessdata else r"C:\Program Files\Tesseract-OCR\tessdata"
        return (
            "Tesseract OCR не найден.\n"
            "Вариант 1: установите с https://github.com/UB-Mannheim/tesseract/wiki "
            "(отметьте Russian language).\n"
            "Вариант 2: положите portable Tesseract в папку tesseract\\ рядом с exe:\n"
            "  tesseract\\tesseract.exe\n"
            "  tesseract\\tessdata\\rus.traineddata\n"
            f"Вариант 3: запустите install_tesseract_rus.bat (скачает rus в {tessdata_hint})"
        )
    return (
        "Tesseract OCR не установлен.\n"
        "macOS: brew install tesseract tesseract-lang\n"
        "Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-rus"
    )


def tesseract_lang_hint(lang: str, missing: list[str]) -> str:
    tessdata = get_tessdata_dir()
    tessdata_hint = str(tessdata) if tessdata else r"C:\Program Files\Tesseract-OCR\tessdata"
    installed = list_installed_tesseract_langs()
    installed_hint = ", ".join(installed[:12]) if installed else "не найдены"
    missing_hint = ", ".join(missing)
    return (
        f"Языковой пакет Tesseract не найден: {missing_hint}\n"
        f"Папка tessdata: {tessdata_hint}\n"
        f"Установленные языки: {installed_hint}\n\n"
        "Как исправить на Windows:\n"
        "  1) Запустите install_tesseract_rus.bat от имени администратора\n"
        "  2) Или переустановите Tesseract и отметьте Russian language:\n"
        "     https://github.com/UB-Mannheim/tesseract/wiki\n"
        "  3) Или скачайте вручную rus.traineddata и положите в tessdata:\n"
        "     https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
    )


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("Ё", "Е").replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.upper().strip()


def normalize_ocr(text: str) -> str:
    return normalize_text(text.translate(OCR_EQUIV))


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "document"
    return name[:max_len]


def render_full_page(page: fitz.Page, dpi: int) -> Image.Image:
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


def detect_skew_angle(gray: np.ndarray, max_angle: float = 15.0) -> float:
    """Оценка небольшого наклона страницы по линиям рамки/текста."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Усиливаем горизонтальные линии рамки
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


def deskew_image(image: Image.Image, max_angle: float = 15.0) -> tuple[Image.Image, float]:
    cv_img = pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    angle = detect_skew_angle(gray, max_angle=max_angle)
    if abs(angle) < 0.2:
        return image, 0.0
    corrected = rotate_bound(cv_img, angle)
    return cv_to_pil(corrected), angle


def parse_osd_rotation(osd_text: str) -> int | None:
    match = re.search(r"Rotate:\s*(\d+)", osd_text)
    if not match:
        return None
    return int(match.group(1)) % 360


def auto_rotate_image(image: Image.Image) -> Image.Image:
    """Поворачивает страницу на 90/180/270°, если скан перевёрнут боком."""
    try:
        osd = pytesseract.image_to_osd(image, config=tessdata_config("--psm 0"))
    except pytesseract.TesseractError:
        return image

    rotation = parse_osd_rotation(osd)
    if rotation in (90, 180, 270):
        return image.rotate(-rotation, expand=True, fillcolor="white")
    return image


def crop_fraction(image: Image.Image, region: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left = int(width * region[0])
    top = int(height * region[1])
    right = int(width * region[2])
    bottom = int(height * region[3])
    return image.crop((left, top, right, bottom))


def ocr_image(image: Image.Image, lang: str) -> str:
    return pytesseract.image_to_string(image, lang=lang, config=tessdata_config())


def prepare_page_image(
    page: fitz.Page,
    dpi: int,
    deskew: bool,
    auto_rotate: bool,
    max_skew: float,
) -> tuple[Image.Image, float | None]:
    image = render_full_page(page, dpi=dpi)
    skew_angle: float | None = None

    if deskew:
        image, skew_angle = deskew_image(image, max_angle=max_skew)

    if auto_rotate:
        image = auto_rotate_image(image)

    return image, skew_angle


def ocr_prepared_page(image: Image.Image, lang: str) -> str:
    """OCR всей страницы + ключевых зон (после выравнивания)."""
    chunks = [
        ocr_image(image, lang=lang),
        ocr_image(crop_fraction(image, CENTER_REGION), lang=lang),
        ocr_image(crop_fraction(image, BOTTOM_LEFT_REGION), lang=lang),
    ]
    return "\n".join(chunks)


def contains_parts(norm: str, *parts: str) -> bool:
    return all(part in norm for part in parts)


def score_title_page(text: str) -> int:
    norm = normalize_ocr(text)
    score = 0

    for parts in STRONG_MARKER_PARTS:
        if contains_parts(norm, *parts):
            score += 4

    for parts in WEAK_MARKER_PARTS:
        if contains_parts(norm, *parts):
            score += 2

    for marker in WEAK_MARKERS:
        if marker in norm:
            score += 1

    if re.search(r"(?:^|\s)ТЛ(?:\s|$)", norm):
        score += 2

    return score


def is_title_page(text: str) -> bool:
    norm = normalize_ocr(text)
    score = score_title_page(text)

    has_strong = any(contains_parts(norm, *parts) for parts in STRONG_MARKER_PARTS)
    has_titul = contains_parts(norm, "ТИТУЛЬН", "ЛИСТ") or re.search(
        r"(?:^|\s)ТЛ(?:\s|$)", norm
    )

    if has_strong:
        return True
    if has_titul and score >= 3:
        return True
    return score >= 5


def extract_doc_number(text: str) -> str | None:
    for pattern in (DOC_NUMBER_RE, ALT_NUMBER_RE):
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def extract_doc_title(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 4:
            continue
        norm = normalize_ocr(line)
        if norm in SKIP_TITLE_LINES:
            continue
        if DOC_NUMBER_RE.search(line) or ALT_NUMBER_RE.search(line):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if "ПИ " in norm or "ДГТУ" in norm or "ФИЛИАЛ" in norm:
            continue
        if len(line) <= 60 and re.search(r"[А-Яа-яA-Za-z]", line):
            return line.strip()
    return None


def get_page_text(
    page: fitz.Page,
    dpi: int,
    lang: str,
    force_ocr: bool,
    deskew: bool,
    auto_rotate: bool,
    max_skew: float,
) -> tuple[str, float | None]:
    if not force_ocr:
        embedded = page.get_text("text")
        if len(embedded.strip()) >= 40:
            return embedded, None

    image, skew_angle = prepare_page_image(
        page,
        dpi=dpi,
        deskew=deskew,
        auto_rotate=auto_rotate,
        max_skew=max_skew,
    )
    return ocr_prepared_page(image, lang=lang), skew_angle


def find_title_pages(
    doc: fitz.Document,
    dpi: int,
    lang: str,
    force_ocr: bool,
    deskew: bool,
    auto_rotate: bool,
    max_skew: float,
    min_score_preview: int = 3,
) -> list[TitlePageInfo]:
    titles: list[TitlePageInfo] = []

    for index in range(doc.page_count):
        page = doc[index]
        text, skew_angle = get_page_text(
            page,
            dpi=dpi,
            lang=lang,
            force_ocr=force_ocr,
            deskew=deskew,
            auto_rotate=auto_rotate,
            max_skew=max_skew,
        )
        score = score_title_page(text)

        if is_title_page(text):
            info = TitlePageInfo(
                page_index=index,
                score=score,
                doc_number=extract_doc_number(text),
                doc_title=extract_doc_title(text),
                skew_angle=skew_angle,
            )
            titles.append(info)
            skew_note = f", наклон={skew_angle:.1f}°" if skew_angle else ""
            print(
                f"  [титульник] стр. {index + 1}: "
                f"score={score}{skew_note}, "
                f"номер={info.doc_number or '—'}, "
                f"название={info.doc_title or '—'}"
            )
        elif score >= min_score_preview:
            print(f"  [пропуск]   стр. {index + 1}: score={score} (ниже порога)")

    return titles


def build_output_name(part_index: int, info: TitlePageInfo) -> str:
    parts = [f"{part_index:03d}"]
    if info.doc_number:
        parts.append(sanitize_filename(info.doc_number.replace(" ", "_")))
    if info.doc_title:
        parts.append(sanitize_filename(info.doc_title))
    else:
        parts.append(f"komplekt_str_{info.page_index + 1}")
    return "_".join(parts) + ".pdf"


def split_pdf(
    input_path: Path,
    output_dir: Path,
    dpi: int,
    lang: str,
    force_ocr: bool,
    deskew: bool,
    auto_rotate: bool,
    max_skew: float,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(input_path) as doc:
        if doc.page_count == 0:
            raise ValueError("PDF пустой")

        print(f"Анализ {doc.page_count} страниц...")
        title_pages = find_title_pages(
            doc,
            dpi=dpi,
            lang=lang,
            force_ocr=force_ocr,
            deskew=deskew,
            auto_rotate=auto_rotate,
            max_skew=max_skew,
        )

        if not title_pages:
            raise RuntimeError(
                "Титульные листы не найдены. Попробуйте --force-ocr, --dpi 250 или --max-skew 20."
            )

        ranges: list[tuple[int, int, TitlePageInfo | None]] = []
        first_title_index = title_pages[0].page_index

        if first_title_index > 0:
            ranges.append((0, first_title_index - 1, None))

        for i, info in enumerate(title_pages):
            start = info.page_index
            end = (
                title_pages[i + 1].page_index - 1
                if i + 1 < len(title_pages)
                else doc.page_count - 1
            )
            ranges.append((start, end, info))

        created: list[Path] = []
        part_num = 1

        for start, end, info in ranges:
            out_doc = fitz.open()
            out_doc.insert_pdf(doc, from_page=start, to_page=end)

            if info is None:
                out_name = f"{part_num:03d}_prefix_pages_{start + 1}-{end + 1}.pdf"
            else:
                out_name = build_output_name(part_num, info)

            out_path = output_dir / out_name
            out_doc.save(out_path)
            out_doc.close()

            page_count = end - start + 1
            print(f"  -> {out_path.name} ({page_count} стр., исходные {start + 1}-{end + 1})")
            created.append(out_path)
            part_num += 1

    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Разбить PDF на комплекты по титульным листам. "
            "Поддерживает кривые сканы: выравнивание наклона и авто-поворот."
        )
    )
    parser.add_argument("input_pdf", type=Path, help="Входной PDF-файл")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Папка для результатов (по умолчанию: <имя_файла>_split)",
    )
    parser.add_argument("--dpi", type=int, default=200, help="DPI для OCR (по умолчанию: 200)")
    parser.add_argument("--lang", default="rus", help="Язык Tesseract (по умолчанию: rus)")
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Всегда OCR, даже если в PDF есть текстовый слой",
    )
    parser.add_argument(
        "--no-deskew",
        action="store_true",
        help="Не выравнивать наклон страницы",
    )
    parser.add_argument(
        "--no-auto-rotate",
        action="store_true",
        help="Не поворачивать страницу на 90/180/270°",
    )
    parser.add_argument(
        "--max-skew",
        type=float,
        default=15.0,
        help="Максимальный исправляемый наклон в градусах (по умолчанию: 15)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Только показать найденные титульники, без сохранения файлов",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input_pdf.is_file():
        print(f"Файл не найден: {args.input_pdf}", file=sys.stderr)
        return 1

    output_dir = args.output_dir or args.input_pdf.with_suffix("").with_name(
        f"{args.input_pdf.stem}_split"
    )

    try:
        if not configure_tesseract():
            raise pytesseract.TesseractNotFoundError()
    except pytesseract.TesseractNotFoundError:
        print(tesseract_install_hint(), file=sys.stderr)
        return 1

    lang_ok, missing_langs = validate_tesseract_lang(args.lang)
    if not lang_ok:
        print(tesseract_lang_hint(args.lang, missing_langs), file=sys.stderr)
        return 1

    try:
        verify_tesseract_runtime(args.lang)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    installed = list_installed_tesseract_langs()
    tessdata = get_tessdata_dir()
    if tessdata:
        print(f"Tesseract tessdata: {tessdata}")
    if installed:
        print(f"Tesseract языки: {', '.join(installed)}")

    deskew = not args.no_deskew
    auto_rotate = not args.no_auto_rotate

    print(f"Вход: {args.input_pdf}")
    print(f"Выход: {output_dir}")
    print(
        f"OCR: dpi={args.dpi}, deskew={'да' if deskew else 'нет'}, "
        f"auto-rotate={'да' if auto_rotate else 'нет'}, max_skew={args.max_skew}°"
    )

    common_kwargs = {
        "dpi": args.dpi,
        "lang": args.lang,
        "force_ocr": args.force_ocr,
        "deskew": deskew,
        "auto_rotate": auto_rotate,
        "max_skew": args.max_skew,
    }

    if args.preview:
        with fitz.open(args.input_pdf) as doc:
            find_title_pages(doc, **common_kwargs)
        print("Режим preview — файлы не созданы.")
        return 0

    try:
        created = split_pdf(
            input_path=args.input_pdf,
            output_dir=output_dir,
            **common_kwargs,
        )
    except (RuntimeError, ValueError, pytesseract.TesseractError) as exc:
        print(f"Ошибка OCR: {exc}", file=sys.stderr)
        message = str(exc).lower()
        if "traineddata" in message or "language" in message:
            _, missing = validate_tesseract_lang(args.lang)
            if missing:
                print(tesseract_lang_hint(args.lang, missing), file=sys.stderr)
        return 1

    print(f"\nГотово: {len(created)} файл(ов) в {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
