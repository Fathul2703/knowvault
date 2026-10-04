"""Builds the PDF documents of the evaluation corpus from their plain-text sources.

    python eval/tools/build_pdf_corpus.py

Each `corpus-src/<name>.txt` becomes `corpus/<name>.pdf`: text wrapped at 90 characters, 48
lines per page, Helvetica, no headings or outline — like a PDF exported from a word processor,
which `pypdf` returns as plain page text. The output is deterministic (no timestamps), so the
committed PDFs can be checked against their sources. Standard library only.
"""

import textwrap
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
SOURCES = EVAL_DIR / "corpus-src"
CORPUS = EVAL_DIR / "corpus"
WIDTH = 90
LINES_PER_PAGE = 48


def _lines(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.strip().split("\n\n"):
        lines.extend(textwrap.wrap(" ".join(paragraph.split()), WIDTH, break_on_hyphens=False))
        lines.append("")
    return lines[:-1]


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text: str) -> bytes:
    lines = _lines(text)
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for index, page in enumerate(pages):
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {page_ids[index] + 1} 0 R >>"
            ).encode()
        )
        shown = " T* ".join(f"({_escape(line)}) Tj" for line in page)
        stream = f"BT /F1 10 Tf 14 TL 56 740 Td {shown} ET".encode("latin-1")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    for source in sorted(SOURCES.glob("*.txt")):
        target = CORPUS / f"{source.stem}.pdf"
        target.write_bytes(make_pdf(source.read_text(encoding="utf-8")))
        print(f"{target.relative_to(EVAL_DIR)}")


if __name__ == "__main__":
    main()
