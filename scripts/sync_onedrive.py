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
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook
from playwright.async_api import async_playwright

SHARE_URL = os.environ.get(
    "ONEDRIVE_FOLDER_URL",
    "https://1drv.ms/f/c/f0437e1066d439c2/IgDmj1ecZZJqR7aps0WECltfAan6hhW4YcCKh7ykiL4Iw9E?e=QPrUMV",
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


async def _download_with_browser(dest: Path) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        await page.goto(SHARE_URL, wait_until="domcontentloaded", timeout=120_000)

        # Give OneDrive's client-side file list time to render.
        await page.wait_for_timeout(8_000)

        # First try the exact visible file name.
        target = page.get_by_text(EXCEL_NAME, exact=True)
        try:
            await target.first.wait_for(state="visible", timeout=30_000)
        except Exception:
            # Search the rendered DOM for anything containing the workbook name.
            target = page.locator(f'text="{EXCEL_NAME}"')
            await target.first.wait_for(state="visible", timeout=30_000)

        # Select the file, then use OneDrive's Download command.
        await target.first.click()
        await page.wait_for_timeout(1_000)

        # Try common localized labels / accessible names.
        download_button = page.get_by_role("button", name=re.compile(r"download|descargar", re.I))
        if await download_button.count() == 0:
            download_button = page.get_by_text(re.compile(r"^\s*(Download|Descargar)\s*$", re.I))

        if await download_button.count() == 0:
            # Double-click often opens Excel Online. From there, the page provides a
            # file-specific URL that can be requested with ?download=1.
            await target.first.dblclick()
            await page.wait_for_timeout(5_000)
            current = page.url
            joiner = "&" if "?" in current else "?"
            r = await context.request.get(current + joiner + "download=1", timeout=120_000)
            body = await r.body()
            if not body.startswith(b"PK"):
                raise RuntimeError("OneDrive no devolvió un archivo XLSX descargable.")
            dest.write_bytes(body)
        else:
            async with page.expect_download(timeout=120_000) as info:
                await download_button.first.click()
            download = await info.value
            await download.save_as(str(dest))

        await browser.close()

    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError("La descarga de OneDrive quedó vacía o incompleta.")


async def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        xlsx = Path(td) / EXCEL_NAME
        await _download_with_browser(xlsx)
        payload = build_json(xlsx)

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
