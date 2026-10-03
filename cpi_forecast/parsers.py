"""Parsers retained from the research implementation."""

import calendar
import io
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader


def parse_release(raw):
    text = "\n".join(
        p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages
    ).replace("−", "-")
    text = re.sub(r"(?<=\d\.)[ \t]+(?=\d)", "", text)
    text = re.sub(r"(?<=\s)r(?=\s[-\d])", "", text)
    labels = {
        "health": "Health insurance",
        "motor": "Motor vehicle insurance",
        "communication": "Communication",
        "apparel": "Apparel",
    }
    out = {}
    for key, label in labels.items():
        candidates = []
        for m in re.finditer(
            r"^\s*" + r"\s+".join(map(re.escape, label.split())), text, re.MULTILINE
        ):
            # Numeric table row can wrap, but cannot cross the next alphabetic label.
            tail = re.split("[A-Za-z]", text[m.end() : m.end() + 400], maxsplit=1)[0]
            # Some older PDFs split every digit with spaces. Match the complete
            # six-cell change row and its known precisions, never merge cells.
            weight = r"\d+\s*\.\s*\d\s*\d\s*\d"
            rate = r"-?\s*\d+\s*\.\s*\d"
            spaced = re.search(
                r"(?<![\d.])(" + weight + ")" + (r"\s+(" + rate + ")") * 5 + r"\s*$",
                tail,
            )
            if spaced:
                tail = tail[: spaced.start()] + " ".join(
                    re.sub(r"\s", "", v) for v in spaced.groups()
                )
            tokens = re.findall(r"(?<!\d)[-]?\d+\.\d+|[–—]", tail)
            numbers = [None if x in ["–", "—"] else float(x) for x in tokens]
            # Detailed index table has 9 numeric entries; detailed change table has 6.
            # Brief narrative/Table A and contribution tables have other shapes.
            if (
                len(numbers) not in [6, 9]
                or numbers[0] is None
                or not 0 < numbers[0] < 10
            ):
                continue
            # Relative importance has three decimals; Table A changes have one.
            if not re.fullmatch(r"\d+\.\d{3}", tokens[0]):
                continue
            rate_tokens = tokens[4:] if len(tokens) == 9 else tokens[1:]
            if any(
                x not in ["–", "—"] and not re.fullmatch(r"-?\d+\.\d", x)
                for x in rate_tokens
            ):
                continue
            # Preserve missing earlier columns as placeholders, never shift them.
            candidates.append(
                {
                    "monthly": numbers[-1],
                    "relative_importance": numbers[0],
                    "excerpt": label + tail.strip(),
                    "numeric_values": numbers,
                }
            )
        if not candidates:
            raise ValueError("No unambiguous detailed row for " + key)
        # Indexed table and detailed change table should agree when both exist.
        first = candidates[0]
        if any(c["monthly"] != first["monthly"] for c in candidates):
            raise ValueError("Conflicting rows for " + key)
        out[key] = first
    return out


def parse_empire(raw, month):
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages]
    if not re.search(
        calendar.month_name[month.month] + r"\s+" + str(month.year), pages[0]
    ):
        raise ValueError(f"Wrong PDF month: {month}")
    text = "\n".join(pages).replace("\u2212", "-").replace("\u2013", "-")
    fields = {
        "empire_prices_paid": r"Prices\s+Paid",
        "empire_prices_received": r"Prices\s+Received",
        "empire_delivery_time": r"Delivery\s+Times?",
    }
    result = {}
    for key, label in fields.items():
        # The first table occurrence is the current reading, before the
        # forward-looking section. Do not confuse it with six-month expectations.
        pattern = (
            label
            + r".{0,250}?\b"
            + calendar.month_abbr[month.month]
            + r"\.?\s+((?:-?\d+\.\d+\s+){2,3}-?\d+\.\d+)"
        )
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse {key}: {month}")
        numbers = [float(v) for v in match[1].split()]
        higher, lower, index = numbers[0], numbers[-2], numbers[-1]
        if not -100 <= index <= 100 or abs(higher - lower - index) > 0.12:
            raise ValueError(
                f"Diffusion-index arithmetic check failed: {month}, {key}, {numbers}"
            )
        result[key] = index
    return result


def xlsx_rows(raw):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(raw)) as z:
        strings = [
            "".join(e.itertext())
            for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)
        ]
        rows = []
        for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).findall(
            "m:sheetData/m:row", ns
        ):
            values = {}
            for c in row.findall("m:c", ns):
                v = c.find("m:v", ns)
                if v is None:
                    continue
                value = strings[int(v.text)] if c.attrib.get("t") == "s" else v.text
                values[re.sub(r"\d", "", c.attrib["r"])] = value
            rows.append(values)
    return rows
