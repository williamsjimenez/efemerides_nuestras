#!/usr/bin/env python3
import argparse
import base64
import json
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EMPTY_TOKENS = {"", "na", "n/a", "none", "null", "pendiente", "no enviaron"}

def present(value):
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in EMPTY_TOKENS:
        return False
    return True

def clean(value):
    if not present(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.strip()
    return value

def excel_serial_to_iso(value):
    try:
        if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
            value = float(value)
        if isinstance(value, (int, float)):
            dt = datetime(1899, 12, 30) + timedelta(days=float(value))
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

def date_value(value):
    if not present(value):
        return None
    iso = excel_serial_to_iso(value)
    if iso:
        return iso
    if isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return s
        return s
    return str(value)

def slugify(text):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "sin-nombre"

def col_index(cell_ref):
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1

def read_shared_strings(zf):
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("main:si", NS):
        out.append("".join((t.text or "") for t in si.iter("{%s}t" % NS["main"])))
    return out

def first_sheet_path(zf):
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("pkgrel:Relationship", NS)}
    sheet = wb.find("main:sheets/main:sheet", NS)
    if sheet is None:
        raise RuntimeError("El Excel no contiene hojas.")
    rid = sheet.attrib.get("{%s}id" % NS["rel"])
    target = relmap[rid]
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return "xl/" + target.lstrip("/")

def parse_hyperlinks(zf, sheet_path, root):
    hyperlinks = {}
    rel_path = str(Path(sheet_path).parent / "_rels" / (Path(sheet_path).name + ".rels")).replace("\\", "/")
    relmap = {}
    try:
        relroot = ET.fromstring(zf.read(rel_path))
        relmap = {r.attrib["Id"]: r.attrib.get("Target") for r in relroot.findall("pkgrel:Relationship", NS)}
    except KeyError:
        pass
    for h in root.findall(".//main:hyperlinks/main:hyperlink", NS):
        ref = h.attrib.get("ref")
        rid = h.attrib.get("{%s}id" % NS["rel"])
        location = h.attrib.get("location")
        target = relmap.get(rid) if rid else location
        if ref and target:
            hyperlinks[ref] = target
    return hyperlinks

def parse_xlsx(path):
    with zipfile.ZipFile(path) as zf:
        shared = read_shared_strings(zf)
        sheet_path = first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
        hyperlinks = parse_hyperlinks(zf, sheet_path, root)
        rows = []
        for row in root.findall(".//main:sheetData/main:row", NS):
            values = {}
            for c in row.findall("main:c", NS):
                ref = c.attrib.get("r")
                if not ref:
                    continue
                idx = col_index(ref)
                t = c.attrib.get("t")
                f = c.find("main:f", NS)
                v = c.find("main:v", NS)
                inline = c.find("main:is/main:t", NS)
                value = None
                if t == "s" and v is not None and v.text is not None:
                    try:
                        value = shared[int(v.text)]
                    except Exception:
                        value = v.text
                elif t == "inlineStr" and inline is not None:
                    value = inline.text or ""
                elif t == "b" and v is not None:
                    value = v.text == "1"
                elif v is not None and v.text is not None:
                    try:
                        num = float(v.text)
                        value = int(num) if num.is_integer() else num
                    except Exception:
                        value = v.text
                if ref in hyperlinks:
                    value = hyperlinks[ref]
                elif f is not None and f.text and f.text.upper().startswith("HYPERLINK("):
                    match = re.search(r'HYPERLINK\(\s*"([^"]+)"', f.text, flags=re.I)
                    if match:
                        value = match.group(1)
                values[idx] = value
            if values:
                width = max(values) + 1
                arr = [None] * width
                for idx, value in values.items():
                    arr[idx] = value
                rows.append(arr)
    if not rows:
        return []
    headers = [str(x).strip() if x is not None else "" for x in rows[0]]
    data = []
    for row in rows[1:]:
        padded = row + [None] * max(0, len(headers) - len(row))
        data.append(dict(zip(headers, padded[:len(headers)])))
    return data

def entity_kind(row):
    nivel = str(clean(row.get("Nivel")) or "").strip().lower()
    programa = clean(row.get("Programa"))
    facultad = clean(row.get("Facultad"))
    sede = clean(row.get("Sede"))
    if nivel == "sede":
        return "Sede"
    if nivel == "instituto":
        return "Instituto"
    if nivel == "facultad":
        return "Facultad"
    if nivel in {"pregrado", "posgrado"}:
        return "Programa"
    if not programa and facultad:
        return "Facultad"
    if not programa and not facultad and sede:
        return "Sede"
    return "Entidad"

def entity_name(row, kind):
    programa = clean(row.get("Programa"))
    facultad = clean(row.get("Facultad"))
    sede = clean(row.get("Sede"))
    if kind == "Sede":
        if facultad and str(facultad).lower().startswith("sede "):
            return str(facultad)
        return f"Sede {sede}" if sede else "Sede"
    if kind == "Programa":
        return programa or "Programa sin nombre"
    if kind in {"Instituto", "Facultad"}:
        return programa or facultad or sede or kind
    return programa or facultad or sede or "Entidad sin nombre"

def make_docs(row, entity_id):
    docs = []
    for i in range(1, 4):
        url = clean(row.get(f"Enlace documento {i}"))
        if not url:
            continue
        url = str(url).strip()
        parsed = urllib.parse.urlparse(url)
        is_pdf = parsed.path.lower().endswith(".pdf")
        docs.append({
            "id": f"{entity_id}-doc-{i}",
            "label": f"Documento {i}",
            "pdf_url": url if is_pdf else None,
            "source_url": url,
            "status": "pdf-disponible" if is_pdf else "documento-enlazado",
        })
    return docs

def build_compact(rows, source_url, acts_folder_url):
    records = []
    source_event_count = 0
    for pos, row in enumerate(rows, start=1):
        rid_raw = clean(row.get("Id"))
        try:
            rid = int(float(rid_raw))
        except Exception:
            rid = pos
        kind = entity_kind(row)
        name = entity_name(row, kind)
        entity_id = f"unal-{rid:03d}-{slugify(name)[:70]}"
        sede = clean(row.get("Sede"))
        facultad = clean(row.get("Facultad"))
        nivel = clean(row.get("Nivel"))
        acto = clean(row.get("Acto administrativo"))
        acto_por = clean(row.get("Acto por"))
        docs = make_docs(row, entity_id)
        status = "con-fuente" if docs else ("con-acto-sin-documento" if acto else "pendiente")
        creation = date_value(row.get("Fecha de creacion"))
        celebration = date_value(row.get("Fecha de celebración"))
        fecha2 = date_value(row.get("Fecha 2"))
        fecha3 = date_value(row.get("Fecha 3"))
        dates = []
        if creation and celebration and creation == celebration:
            dates.append(["Creación y celebración", creation])
        else:
            if creation:
                dates.append(["Creación", creation])
            if celebration:
                dates.append(["Celebración institucional", celebration])
        if fecha2:
            dates.append(["Fecha histórica complementaria 2", fecha2])
        if fecha3:
            dates.append(["Fecha histórica complementaria 3", fecha3])
        seen = set()
        deduped = []
        for label, value in dates:
            key = (label, str(value))
            if key not in seen:
                seen.add(key)
                deduped.append([label, value])
        source_event_count += len(deduped)
        records.append([
            entity_id, name, kind, sede, facultad, nivel, acto, acto_por,
            docs, status, deduped
        ])
    return {
        "m": {
            "records": len(records),
            "events": source_event_count,
            "source_excel_url": source_url,
            "acts_folder_url": acts_folder_url,
            "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "r": records,
    }

def fetch_bytes(url, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl(), resp.headers.get("Content-Type", "")

def download_via_personal_onedrive_api(source_url, output_path):
    token_body = json.dumps({"appId": "5cbed6ac-a083-4e14-b191-b4ba07653de2"}).encode("utf-8")
    token_bytes, _, _ = fetch_bytes(
        "https://api-badgerp.svc.ms/v1.0/token",
        headers={
            "User-Agent": "Mozilla/5.0 EfemeridesUNALSync/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=token_body,
    )
    token_payload = json.loads(token_bytes.decode("utf-8"))
    badger_token = token_payload.get("token")
    if not badger_token:
        raise RuntimeError("OneDrive no devolvió el token temporal de acceso.")

    encoded = base64.urlsafe_b64encode(source_url.encode("utf-8")).decode("ascii").rstrip("=")
    api_url = (
        "https://my.microsoftpersonalcontent.com/_api/v2.0/shares/"
        f"u!{encoded}/driveitem?select=@content.downloadUrl,name"
    )
    item_bytes, _, _ = fetch_bytes(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 EfemeridesUNALSync/1.0",
            "Accept": "application/json",
            "Prefer": "autoredeem",
            "Authorization": f"Badger {badger_token}",
        },
    )
    item = json.loads(item_bytes.decode("utf-8"))
    download_url = item.get("@content.downloadUrl")
    if not download_url:
        raise RuntimeError("OneDrive no devolvió @content.downloadUrl para el Excel compartido.")

    try:
        data, final_url, content_type = fetch_bytes(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 EfemeridesUNALSync/1.0"},
        )
    except Exception:
        parsed = urllib.parse.urlparse(download_url)
        tempauth = urllib.parse.parse_qs(parsed.query).get("tempauth", [None])[0]
        if not tempauth:
            raise
        data, final_url, content_type = fetch_bytes(
            download_url,
            headers={
                "User-Agent": "Mozilla/5.0 EfemeridesUNALSync/1.0",
                "Authorization": f"Bearer {tempauth}",
            },
        )

    if not data.startswith(b"PK\x03\x04"):
        raise RuntimeError(
            f"La URL temporal de OneDrive no devolvió un XLSX válido ({content_type}, {len(data)} bytes)."
        )
    output_path.write_bytes(data)
    return {
        "method": "onedrive-personal-api",
        "final_url": final_url,
        "content_type": content_type,
        "bytes": len(data),
        "file_name": item.get("name"),
    }

def download_xlsx(source_url, output_path):
    parsed = urllib.parse.urlparse(source_url)
    qs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    candidates = []
    if not any(k.lower() == "download" for k, _ in qs):
        qs_dl = qs + [("download", "1")]
        candidates.append(urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(qs_dl))))
    candidates.append(source_url)

    errors = []
    for url in candidates:
        try:
            data, final_url, content_type = fetch_bytes(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 EfemeridesUNALSync/1.0",
                    "Accept": "*/*",
                },
            )
            if data.startswith(b"PK\x03\x04"):
                output_path.write_bytes(data)
                return {
                    "method": "direct",
                    "requested_url": url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "bytes": len(data),
                }
            errors.append(f"{url}: respuesta no XLSX ({content_type}, {len(data)} bytes)")
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    try:
        return download_via_personal_onedrive_api(source_url, output_path)
    except Exception as exc:
        errors.append(f"OneDrive Personal API: {exc}")

    raise RuntimeError("No se pudo descargar un XLSX válido desde OneDrive. " + " | ".join(errors))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="data/source-config.json")
    ap.add_argument("--local-xlsx", default=None)
    ap.add_argument("--output", default="data/live.txt")
    ap.add_argument("--manifest", default="data/manifest.json")
    args = ap.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    source_url = config["excel_url"]
    acts_folder_url = config.get("acts_folder_url")
    local = Path(args.local_xlsx) if args.local_xlsx else Path(".sync/efemerides.xlsx")
    local.parent.mkdir(parents=True, exist_ok=True)
    if args.local_xlsx:
        dl_info = {"local_xlsx": str(local)}
    else:
        dl_info = download_xlsx(source_url, local)
    rows = parse_xlsx(local)
    if not rows:
        raise RuntimeError("El archivo descargado no contiene registros.")
    raw = build_compact(rows, source_url, acts_folder_url)
    Path(args.output).write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    manifest = {
        "parts": [args.output],
        "records": raw["m"]["records"],
        "source_events": raw["m"]["events"],
        "source": source_url,
        "acts_folder_url": acts_folder_url,
        "synced_at": raw["m"]["synced_at"],
    }
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "download": dl_info,
        "records": raw["m"]["records"],
        "source_events": raw["m"]["events"],
        "output": args.output,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
