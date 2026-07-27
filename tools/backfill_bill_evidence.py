from __future__ import annotations

import argparse
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "shandong_quota.sqlite"
OCR_CACHE = PROJECT_ROOT / "build" / "evidence-ocr-50854.json"
TESSERACT = PROJECT_ROOT / "tools" / "Tesseract-OCR" / "tesseract.exe"

SPECS = {
    "building": ("50854", True),
    "installation": ("50856", False),
    "municipal": ("50857", False),
    "landscape": ("50858", False),
}


def _compact(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value or ""))


def _base_code(value: object) -> str:
    match = re.search(r"(?<!\d)(\d{9})(?!\d)", str(value or ""))
    return match.group(1) if match else ""


def _source_for(source_dir: Path, marker: str) -> Path:
    matches = sorted({path.resolve() for path in source_dir.glob(f"*{marker}*.[pP][dD][fF]")})
    if len(matches) != 1:
        raise RuntimeError(f"{marker} 应匹配一本 PDF，实际 {len(matches)} 本")
    return matches[0].resolve()


def _extract_searchable_pages(path: Path) -> dict[int, dict[str, object]]:
    from pypdf import PdfReader

    pages: dict[int, dict[str, object]] = {}
    for number, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = page.extract_text() or ""
        compact = re.sub(r"\s+", "", text)
        codes = set(re.findall(r"(?<!\d)(\d{9})(?!\d)", compact))
        pages[number] = {"codes": sorted(codes), "text": text}
    return pages


def _ocr_one_page(path: Path, page_index: int) -> tuple[int, dict[str, object]]:
    import fitz
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
    document = fitz.open(path)
    try:
        page = document[page_index]
        matrix = fitz.Matrix(3.5, 3.5)
        full_pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
        full_image = Image.frombytes("L", (full_pixmap.width, full_pixmap.height), full_pixmap.samples)
        full_text = pytesseract.image_to_string(full_image, lang="chi_sim+eng", config="--psm 11")

        rect = page.rect
        clip = fitz.Rect(rect.x0, rect.y0, rect.x0 + rect.width * 0.38, rect.y1)
        code_pixmap = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip, colorspace=fitz.csGRAY, alpha=False)
        code_image = Image.frombytes("L", (code_pixmap.width, code_pixmap.height), code_pixmap.samples)
        digit_text = pytesseract.image_to_string(
            code_image,
            lang="eng",
            config="--psm 6 -c tessedit_char_whitelist=0123456789",
        )
        codes = set(re.findall(r"(?<!\d)(\d{9})(?!\d)", full_text + "\n" + digit_text))
        return page_index + 1, {"codes": sorted(codes), "text": full_text}
    finally:
        document.close()


def _extract_scanned_pages(path: Path, workers: int) -> dict[int, dict[str, object]]:
    if OCR_CACHE.exists():
        cached = json.loads(OCR_CACHE.read_text(encoding="utf-8"))
        if cached.get("source_size") == path.stat().st_size and cached.get("source_mtime_ns") == path.stat().st_mtime_ns:
            return {int(key): value for key, value in cached["pages"].items()}

    import fitz

    if not TESSERACT.is_file():
        raise FileNotFoundError(f"未找到 OCR 程序：{TESSERACT}")
    with fitz.open(path) as document:
        page_count = document.page_count
    pages: dict[int, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_ocr_one_page, path, index) for index in range(page_count)]
        for completed, future in enumerate(as_completed(futures), start=1):
            page, payload = future.result()
            pages[page] = payload
            if completed % 10 == 0 or completed == page_count:
                print(f"OCR {completed}/{page_count}", flush=True)
    OCR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OCR_CACHE.write_text(json.dumps({
        "source": str(path),
        "source_size": path.stat().st_size,
        "source_mtime_ns": path.stat().st_mtime_ns,
        "pages": pages,
    }, ensure_ascii=False), encoding="utf-8")
    return pages


def _page_map(rows: list[sqlite3.Row], pages: dict[int, dict[str, object]]) -> tuple[dict[str, int], dict[str, str]]:
    database_titles = {_base_code(row["code"]): str(row["title"] or "") for row in rows}
    database_codes = {code for code in database_titles if code}
    compact_page_text = {page: _compact(payload.get("text")) for page, payload in pages.items()}
    located: dict[str, int] = {}
    methods: dict[str, str] = {}
    for page, payload in pages.items():
        for code in set(payload.get("codes") or []) & database_codes:
            located.setdefault(code, page)
            methods.setdefault(code, "code")

    ordered = [code for code in database_titles if code]
    for index, code in enumerate(ordered):
        if code in located:
            continue
        previous = next((located[ordered[pos]] for pos in range(index - 1, -1, -1) if ordered[pos] in located), None)
        following = next((located[ordered[pos]] for pos in range(index + 1, len(ordered)) if ordered[pos] in located), None)
        title = _compact(database_titles[code])
        if title:
            hits = [page for page, text in compact_page_text.items() if title in text]
            bounded = [page for page in hits if (previous is None or page >= previous) and (following is None or page <= following)]
            if len(bounded) == 1:
                located[code] = bounded[0]
                methods[code] = "title"
                continue
        if previous is not None and previous == following:
            located[code] = previous
            methods[code] = "bounded_same_page"
    return located, methods


def run(database: Path, source_dir: Path, *, apply: bool, workers: int) -> dict[str, object]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    report: dict[str, object] = {}
    try:
        for discipline, (marker, scanned) in SPECS.items():
            source = _source_for(source_dir, marker)
            rows = list(connection.execute(
                "SELECT chunk_id,code,title FROM chunks "
                "WHERE chunk_type='bill_item' AND edition='2024' AND discipline=? ORDER BY code,chunk_id",
                (discipline,),
            ))
            pages = _extract_scanned_pages(source, workers) if scanned else _extract_searchable_pages(source)
            located, methods = _page_map(rows, pages)
            missing = sorted({_base_code(row["code"]) for row in rows} - set(located))
            report[discipline] = {
                "total": len(rows),
                "located": len(located),
                "missing": missing,
                "methods": {method: list(methods.values()).count(method) for method in sorted(set(methods.values()))},
                "source": str(source),
            }
            print(f"{discipline}: {len(located)}/{len(rows)} located; missing={len(missing)}")
            if apply:
                updates = [
                    (str(source), located[code], str(row["chunk_id"]))
                    for row in rows
                    for code in [_base_code(row["code"])]
                    if code in located
                ]
                connection.executemany(
                    "UPDATE chunks SET source_path=?,pdf_page=? WHERE chunk_id=?",
                    updates,
                )
        if apply:
            connection.commit()
    finally:
        connection.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill 2024 bill-item PDF evidence pages")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Directory containing the authorized GBT 50854/50856/50857/50858 PDFs",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run(args.database.resolve(), args.source_dir.resolve(), apply=args.apply, workers=args.workers)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
