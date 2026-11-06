"""Turn a downloaded file into text the agent can read: CSV/TSV as a table, Excel's first sheets,
PDF text, and plain text formats. Files come from websites, so this only ever reads them."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TEXT_TYPES = {
    ".txt",
    ".log",
    ".md",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".ics",
    ".vcf",
    ".yaml",
    ".yml",
    ".srt",
    ".vtt",
}
MAX_UNZIPPED = 50 * 1024 * 1024  # an .xlsx that unpacks bigger than this isn't read


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name).strip(". ")[:120]
    return name or "download"


def decode(data: bytes) -> str:
    for enc in ("utf-16", "utf-8-sig") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("cp1252", errors="replace")


def table(rows: list[list[str]], max_rows: int = 200) -> str:
    """Rows -> a Markdown table (first row is the header)."""
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return "(empty)"
    width = max(len(r) for r in rows)

    def cell(c: str) -> str:
        c = " ".join(c.split()).replace("|", "\\|")
        return c[:80] + "…" if len(c) > 80 else c

    lines = []
    for i, r in enumerate(rows[: max_rows + 1]):
        lines.append("| " + " | ".join(cell(c) for c in r + [""] * (width - len(r))) + " |")
        if i == 0:
            lines.append("|" + " --- |" * width)
    if len(rows) > max_rows + 1:
        lines.append(f"(+{len(rows) - max_rows - 1} more rows; the full file is saved)")
    return "\n".join(lines)


def _csv(text: str, delimiter: str | None) -> str:
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    return table(list(csv.reader(io.StringIO(text), delimiter=delimiter)))


def _xlsx(data: bytes) -> str:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
            return "(spreadsheet too big to read; the full file is saved)"

        def xml(name: str):
            return ElementTree.fromstring(z.read(name)) if name in z.namelist() else None

        shared = []
        sst = xml("xl/sharedStrings.xml")
        if sst is not None:
            shared = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in sst.findall("m:si", ns)]
        book, rels = xml("xl/workbook.xml"), xml("xl/_rels/workbook.xml.rels")
        targets = {r.get("Id"): r.get("Target") for r in rels} if rels is not None else {}
        sheets = []
        for sh in book.findall("m:sheets/m:sheet", ns) if book is not None else []:
            target = targets.get(sh.get(rel), "")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            sheets.append((sh.get("name"), target))
        out = []
        for name, path in sheets[:5]:
            root = xml(path)
            if root is None:
                continue
            rows = []
            for row in root.iter(f"{{{ns['m']}}}row"):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", ns):
                    col = _col(c.get("r", ""))
                    v = c.find("m:v", ns)
                    kind = c.get("t")
                    if kind == "s" and v is not None:
                        val = shared[int(v.text)] if v.text and v.text.isdigit() and int(v.text) < len(shared) else ""
                    elif kind == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
                    else:
                        val = v.text if v is not None and v.text else ""
                    cells[col if col >= 0 else len(cells)] = val
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            out.append(f"### Sheet: {name}\n{table(rows)}")
        if len(sheets) > 5:
            out.append(f"(+{len(sheets) - 5} more sheets)")
        return "\n\n".join(out) or "(no sheets found)"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "(PDF saved; text extraction isn't available here)"
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return "(the PDF is password-protected)"
    parts = []
    for i, page in enumerate(reader.pages[:100]):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"--- page {i + 1} ---\n{text}")
    if len(reader.pages) > 100:
        parts.append(f"(+{len(reader.pages) - 100} more pages)")
    return "\n\n".join(parts) or "(no text in this PDF; it may be scanned images)"


def _html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def read(path: Path, content_type: str = "") -> str | None:
    """Readable text for a file, or None for kinds it can't read (images, archives, ...)."""
    ext = path.suffix.lower()
    ctype = content_type.split(";")[0].strip().lower()
    data = path.read_bytes()
    if ext == ".pdf" or ctype == "application/pdf" or data[:5] == b"%PDF-":
        return _pdf(path)
    if ext in (".xlsx", ".xlsm") or "spreadsheetml" in ctype:
        try:
            return _xlsx(data)
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError):
            return None
    if ext in (".csv", ".tsv") or ctype in ("text/csv", "text/tab-separated-values"):
        return _csv(decode(data), "\t" if ext == ".tsv" else None)
    if ext in (".html", ".htm") or ctype == "text/html":
        return _html(decode(data))
    if ext in TEXT_TYPES or ctype.startswith("text/") or ctype in ("application/json", "application/xml"):
        return decode(data)
    return None
