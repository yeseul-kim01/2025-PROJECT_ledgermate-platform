from __future__ import annotations
from bs4 import BeautifulSoup

def extract_tables_from_html(html_str: str):
    soup = BeautifulSoup(html_str or "", "html.parser")
    out = []
    for idx, tbl in enumerate(soup.find_all("table")):
        caption_tag = tbl.find("caption")
        caption = caption_tag.get_text(" ", strip=True) if caption_tag else None

        rows, header_rows = [], 0
        def _read(section, is_header=False):
            nonlocal header_rows
            if not section: return
            for tr in section.find_all("tr"):
                row = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th","td"], recursive=False)]
                rows.append(row)
                if is_header: header_rows += 1

        _read(tbl.find("thead"), is_header=True)
        _read(tbl.find("tbody"), is_header=False)
        if not rows:  # thead/tbody 없을 때
            for tr in tbl.find_all("tr", recursive=False):
                rows.append([cell.get_text(" ", strip=True) for cell in tr.find_all(["th","td"], recursive=False)])

        spans = []
        for r, tr in enumerate(tbl.find_all("tr", recursive=False)):
            for c, cell in enumerate(tr.find_all(["th","td"], recursive=False)):
                rs = int(cell.get("rowspan") or 1)
                cs = int(cell.get("colspan") or 1)
                if rs > 1 or cs > 1:
                    spans.append({"r": r, "c": c, "rowspan": rs, "colspan": cs})

        out.append({
            "id": f"table-{idx}",
            "caption": caption,
            "rows": rows,
            "header_rows": header_rows,
            "row_count": len(rows),
            "col_count": max((len(r) for r in rows), default=0),
            "spans": spans or None,
            "source": "html",
        })
    return out

def table_to_text(rows):
    return "\n".join("\t".join(c or "" for c in row) for row in rows)
