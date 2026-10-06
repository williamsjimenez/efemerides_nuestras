#!/usr/bin/env python3
"""
Synchronize data/universidades.json from the master Excel stored in the
publicly shared OneDrive folder used by the efemérides project.

The script deliberately does not store Microsoft credentials. It uses the
existing anonymous folder link and downloads the workbook in a browser
session. If the workbook has not changed, the generated JSON remains byte-for-byte
identical (except when data changes), so GitHub will not create a needless commit.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

SHARE_URL = os.environ.get(
    "ONEDRIVE_EXCEL_URL",
    "https://1drv.ms/x/c/f0437e1066d439c2/IQAv66Gk4KVHSZa9AhJwlOicAUruLJtLe7NfeEkDBUGDljc?e=YIcR7d",
)
EXCEL_NAME = os.environ.get(
    "ONEDRIVE_EXCEL_NAME",
    "Repositorio_Maestro_Efemerides_Universitarias.xlsx",
)
OUTPUT = Path(os.environ.get("OUTPUT_JSON", "data/universidades.json"))


def norm(value):
    if value is None:
        return ""
    return str(value).strip()


def num(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        m = re.search(r"\d+", str(value))
        return int(m.group()) if m else None


def build_json(xlsx_path: Path) -> dict:
    wb = load_workbook(xlsx_path, data_only=True, read_only=True)
    if "Maestro" not in wb.sheetnames:
        raise RuntimeError("El Excel no contiene la hoja 'Maestro'.")
    ws = wb["Maestro"]

    # Find the header row instead of assuming a fixed position.
    header_row = None
    headers = {}
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 20), values_only=True):
        values = [norm(v) for v in row]
        if "Nombre universidad / institución" in values:
            header_row = row
            headers = {norm(v): i for i, v in enumerate(row) if norm(v)}
            break
    if header_row is None:
        raise RuntimeError("No se encontró la fila de encabezados del repositorio maestro.")

    required = [
        "Nombre universidad / institución",
        "País",
        "Año de fundación",
        "Día de fundación",
        "N.º mes",
        "Rector 2026",
        "Rector 2027",
        "Rector 2028",
        "Tipo de entidad",
    ]
    missing = [h for h in required if h not in headers]
    if missing:
        raise RuntimeError("Faltan columnas requeridas: " + ", ".join(missing))

    # Determine the actual Excel row number of the header.
    header_idx = None
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 20), values_only=True), start=1):
        if any(norm(v) == "Nombre universidad / institución" for v in row):
            header_idx = i
            break

    institutions = []
    for row in ws.iter_rows(min_row=header_idx + 1, values_only=True):
        name = norm(row[headers["Nombre universidad / institución"]])
        if not name:
            continue
        country = norm(row[headers["País"]])
        year = num(row[headers["Año de fundación"]])
        day = num(row[headers["Día de fundación"]])
        month = num(row[headers["N.º mes"]])
        typ = norm(row[headers["Tipo de entidad"]]) or "Universidad"
        if not (year and day and month):
            # A record without a complete day/month/year cannot be placed in the calendar.
            continue

        institutions.append({
            "name": name,
            "country": country,
            "foundation_year": year,
            "day": day,
            "month": month,
            "rectors": {
                "2026": norm(row[headers["Rector 2026"]]),
                "2027": norm(row[headers["Rector 2027"]]),
                "2028": norm(row[headers["Rector 2028"]]),
            },
            "type": typ,
        })

    institutions.sort(key=lambda x: (x["month"], x["day"], x["name"].casefold()))
    return {
        "meta": {
            "title": "Efemérides universitarias",
            "source": EXCEL_NAME,
            "records": len(institutions),
            "synced_from_onedrive": True,
        },
        "institutions": institutions,
    }


def _fetch_bytes(url: str, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl(), resp.headers.get("Content-Type", "")


def _download_direct_onedrive(dest: Path) -> None:
    token_body = json.dumps({"appId": "5cbed6ac-a083-4e14-b191-b4ba07653de2"}).encode("utf-8")
    token_bytes, _, _ = _fetch_bytes(
        "https://api-badgerp.svc.ms/v1.0/token",
        headers={
            "User-Agent": "Mozilla/5.0 EfemeridesUniversitarias/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=token_body,
    )
    token_payload = json.loads(token_bytes.decode("utf-8"))
    badger_token = token_payload.get("token")
    if not badger_token:
        raise RuntimeError("OneDrive no devolvió el token temporal.")

    encoded = base64.urlsafe_b64encode(SHARE_URL.encode("utf-8")).decode("ascii").rstrip("=")
    api_url = (
        "https://my.microsoftpersonalcontent.com/_api/v2.0/shares/"
        f"u!{encoded}/driveitem?select=@content.downloadUrl,name"
    )
    item_bytes, _, _ = _fetch_bytes(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 EfemeridesUniversitarias/1.0",
            "Accept": "application/json",
            "Prefer": "autoredeem",
            "Authorization": f"Badger {badger_token}",
        },
    )
    item = json.loads(item_bytes.decode("utf-8"))
    download_url = item.get("@content.downloadUrl")
    if not download_url:
        raise RuntimeError("OneDrive no devolvió una URL de descarga para el Excel.")

    data, _, content_type = _fetch_bytes(
        download_url,
        headers={"User-Agent": "Mozilla/5.0 EfemeridesUniversitarias/1.0"},
        timeout=120,
    )
    if not data.startswith(b"PK\x03\x04"):
        raise RuntimeError(
            f"OneDrive no devolvió un XLSX válido ({content_type}, {len(data)} bytes)."
        )
    dest.write_bytes(data)

    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError("La descarga de OneDrive quedó vacía o incompleta.")


async def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        xlsx = Path(td) / EXCEL_NAME
        _download_direct_onedrive(xlsx)
        payload = build_json(xlsx)
        print(f"Fuente OneDrive descargada: {len(payload['institutions'])} registros válidos.")

    # Preserve a stable file when no data changed. This allows the workflow to
    # poll frequently without generating empty commits.
    current = None
    if OUTPUT.exists():
        try:
            current = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:
            current = None

    if current and current.get("institutions") == payload.get("institutions"):
        print(f"Sin cambios: {len(payload['institutions'])} registros.")
        return

    payload["meta"]["last_sync_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Actualizado: {len(payload['institutions'])} registros -> {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
