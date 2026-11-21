"""Minimal .xlsx reader (standard library only): worksheets as lists of {column letter: value}."""

import re
import zipfile
from xml.etree import ElementTree as ET

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def xlsx_rows(path):
    """Return (zip member names, {sheet path: [row dict, ...]}) with shared strings resolved."""
    ns = {"m": NS}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        strings = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                strings.append("".join(t.text or "" for t in si.iter("{%s}t" % NS)))
        sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        out = {}
        for sh in sheets:
            root = ET.fromstring(z.read(sh))
            rows = []
            for row in root.iter("{%s}row" % NS):
                cells = {}
                for c in row.findall("m:c", ns):
                    ref = re.match(r"[A-Z]+", c.get("r", "A")).group(0)
                    v = c.find("m:v", ns)
                    t = c.get("t")
                    if t == "s" and v is not None:
                        val = strings[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter("{%s}t" % NS))
                    else:
                        val = v.text if v is not None else None
                    cells[ref] = val
                rows.append(cells)
            out[sh] = rows
        return names, out
