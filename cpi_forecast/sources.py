"""Download the public sources listed in a versioned manifest. No API keys needed."""

import csv
import gzip
import hashlib
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from pypdf import PdfReader

from .parsers import parse_empire, parse_release, xlsx_rows
from .report import write_json


def fetch(url, cache, fields=None, offline=False):
    body = urlencode(fields).encode() if fields is not None else None
    key = hashlib.sha256(url.encode() + b"\n" + (body or b"")).hexdigest()
    path = Path(cache) / key
    meta_path = path.with_suffix(".json")
    if path.exists() and meta_path.exists():
        raw, meta = path.read_bytes(), json.loads(meta_path.read_text(encoding="utf-8"))
        if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
            raise ValueError("Cache file changed: " + str(path))
        return raw, meta
    if offline:
        raise FileNotFoundError("Missing offline source: " + url)
    headers = {} if "alfred.stlouisfed.org" in url else {"User-Agent": "Mozilla/5.0"}
    for attempt in range(3):
        try:
            with urlopen(
                Request(url, data=body, headers=headers), timeout=45
            ) as response:
                raw = response.read()
            break
        except HTTPError as exc:
            if exc.code in (401, 403, 404) or attempt == 2:
                raise
            time.sleep(1 + attempt)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    meta = {
        "url": url,
        "form_body": body.decode() if body else None,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    write_json(meta_path, meta)
    return raw, meta


def parse_matrix(raw, series):
    result = {}
    with ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            reader = csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig")))
            if not reader.fieldnames or reader.fieldnames[0] != "observation_date":
                raise ValueError("Unexpected ALFRED matrix header")
            columns = {}
            for column in reader.fieldnames[1:]:
                if not column.startswith(series + "_"):
                    raise ValueError("Unexpected series: " + column)
                vintage = (
                    datetime.strptime(column[len(series) + 1 :], "%Y%m%d")
                    .date()
                    .isoformat()
                )
                if vintage in result:
                    raise ValueError("Duplicate vintage: " + vintage)
                columns[column] = vintage
                result[vintage] = {}
            for row in reader:
                for col, vintage in columns.items():
                    result[vintage][row["observation_date"]] = (
                        None if row[col] in ("", ".") else float(row[col])
                    )
    return result


def collect_series(spec, cache, offline):
    snapshots, evidence = {}, []
    for i in range(0, len(spec["vintages"]), 30):
        batch = spec["vintages"][i : i + 30]
        fields = [
            ("form[units]", "lin"),
            ("form[obs_start_date]", spec["start"]),
            ("form[obs_end_date]", spec["end"]),
            ("form[file_type]", "2"),
            ("form[file_format]", "csv"),
            ("form[download_data]", ""),
            ("form[entered_vintage_dates]", " ".join(batch)),
        ]
        raw, meta = fetch(
            "https://alfred.stlouisfed.org/series/downloaddata?seid=" + spec["series"],
            cache,
            fields,
            offline,
        )
        parsed = parse_matrix(raw, spec["series"])
        if set(parsed) != set(batch):
            raise ValueError("Missing or unexpected ALFRED vintages: " + spec["series"])
        snapshots.update(parsed)
        evidence.append(meta)
    return snapshots, evidence


def parse_weights(raw):
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages)
    labels = {
        "rent": r"Rent of primary residence",
        "oer": r"Owners[’\x27] equivalent rent of\s+residences",
        "used": r"Used cars and trucks",
        "air": r"Airline fares?",
        "hotel": r"Lodging away from home",
        "medical": r"Medical care services",
        "core": r"All items less food and energy",
    }
    values = {}
    for key, label in labels.items():
        match = re.search(
            label
            + r"[.\s\d,]*?([0-9](?:\s*[0-9])*\s*\.\s*[0-9]\s*[0-9]\s*[0-9])(?=\s)",
            text,
        )
        if not match:
            raise ValueError("Cannot parse BLS weight: " + key)
        values[key] = float(re.sub(r"\s", "", match[1]))
    weights = {k: v / values["core"] for k, v in values.items() if k != "core"}
    weights["remainder"] = 1 - sum(weights.values())
    if not all(0 < v < 1 for v in weights.values()):
        raise ValueError("Invalid BLS weight partition")
    return weights


def collect(manifest, cache, offline=False):
    Path(cache).mkdir(parents=True, exist_ok=True)
    # Check access before queueing hundreds of downloads. Offline mode skips
    # HTML checks and needs only the actual cached data requests.
    if not offline:
        try:
            core = manifest["alfred"]["core"]
            collect_series({**core, "vintages": core["vintages"][:30]}, cache, False)
            fetch(next(iter(manifest["health"].values()))["url"], cache)
        except HTTPError as exc:
            audit = {
                "status": "access_check_failed",
                "url": exc.url,
                "http_status": exc.code,
            }
            write_json(Path(cache) / "access_check.json", audit)
            raise ValueError(
                f"Source access check failed (HTTP {exc.code}): {exc.url}. "
                "Use the bundled-data reproduce command; the download cannot complete on this connection."
            ) from exc
    observations = {"snapshots": {}, "factory": {}, "health": {}, "weights": {}}
    evidence, changed_sources = [], []
    jobs = [("alfred", name, spec) for name, spec in manifest["alfred"].items()]
    jobs += [
        (group, name, spec)
        for group in ("factory", "health", "weights")
        for name, spec in manifest[group].items()
    ]
    jobs += [(name, name, manifest[name]) for name in ("zori", "manheim")]

    def run(job):
        group, name, spec = job
        if group == "alfred":
            values, meta = collect_series(spec, cache, offline)
            return group, name, values, meta, False
        raw, meta = fetch(spec["url"], cache, offline=offline)
        changed = meta["sha256"] != spec["sha256"]
        if group == "factory":
            values = {
                **spec,
                "value": parse_empire(raw, date.fromisoformat(name))[
                    "empire_prices_paid"
                ],
            }
        elif group == "health":
            values = {**spec, "value": parse_release(raw)["health"]["monthly"]}
        elif group == "weights":
            values = {**spec, "values": parse_weights(raw)}
        elif group == "zori":
            rows = [
                r
                for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
                if r["RegionName"] == "United States"
            ]
            if len(rows) != 1:
                raise ValueError("Expected one national ZORI row")
            values = {
                k[:7] + "-01": float(v)
                for k, v in rows[0].items()
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", k) and v
            }
        else:
            values = {}
            for r in xlsx_rows(raw)[1:]:
                if r.get("A") and r.get("B"):
                    month = (
                        (datetime(1899, 12, 30) + timedelta(days=float(r["A"])))
                        .date()
                        .replace(day=1)
                    )
                    values[str(month)] = float(r["B"])
        if group in ("factory", "health", "weights"):
            values["sha256"] = meta["sha256"]
        return group, name, values, [meta], changed

    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run, job): job for job in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                group, name, values, meta, changed = future.result()
                if group == "alfred":
                    observations["snapshots"][name] = values
                elif group in ("zori", "manheim"):
                    observations[group] = values
                else:
                    observations[group][name] = values
                evidence.extend(meta)
                if changed:
                    changed_sources.append(
                        {"group": group, "name": name, "url": meta[0]["url"]}
                    )
                if group == "alfred" or count % 25 == 0:
                    print(
                        f"Downloaded/parsed {count}/{len(jobs)} source jobs ({group}: {name})",
                        flush=True,
                    )
            except Exception as exc:
                errors.append({"job": futures[future][:2], "error": str(exc)})
                print(f"Source failed: {futures[future][:2]}: {exc}", flush=True)
                # A partial dataset cannot reproduce this study. Stop queued
                # work promptly instead of repeating an access failure hundreds
                # of times; completed downloads remain available for a retry.
                for pending in futures:
                    pending.cancel()
                break
    audit = {
        "source_jobs": len(jobs),
        "requests": len(evidence),
        "sources": evidence,
        "changed_sources": changed_sources,
        "errors": errors,
    }
    write_json(Path(cache) / "audit.json", audit)
    if errors:
        raise ValueError(
            f"Download stopped after a source failure. See {Path(cache) / 'audit.json'}; retry uses verified cached downloads."
        )
    return observations, audit


def save_observations(path, observations):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        gzip.compress(
            json.dumps(observations, separators=(",", ":"), allow_nan=False).encode(),
            mtime=0,
        )
    )
