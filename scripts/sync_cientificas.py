#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from openpyxl import load_workbook
from playwright.async_api import async_playwright

SOURCE_URL=os.environ.get("SCIENTIFIC_ONEDRIVE_URL","https://1drv.ms/x/c/f0437e1066d439c2/IQAG-oAXUhAgR6GLr-icPyUEAV8yn94El0QRd_kLoOFteuE?e=D0fVWv")
OUTPUT=Path(os.environ.get("SCIENTIFIC_OUTPUT_JSON","data/cientificas.json"))
MONTHS={"Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6,"Julio":7,"Agosto":8,"Septiembre":9,"Octubre":10,"Noviembre":11,"Diciembre":12,"Dicimbre":12}

def norm(v): return "" if v is None else str(v).strip()

async def download(dest:Path):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        ctx=await browser.new_context(accept_downloads=True)
        page=await ctx.new_page()
        await page.goto(SOURCE_URL,wait_until="domcontentloaded",timeout=120000)
        await page.wait_for_timeout(7000)
        btn=page.get_by_role("button",name=re.compile(r"download|descargar",re.I))
        if await btn.count()==0:
            btn=page.get_by_text(re.compile(r"^\s*(Download|Descargar)\s*$",re.I))
        if await btn.count():
            async with page.expect_download(timeout=120000) as info:
                await btn.first.click()
            dl=await info.value
            await dl.save_as(str(dest))
        else:
            current=page.url
            sep="&" if "?" in current else "?"
            resp=await ctx.request.get(current+sep+"download=1",timeout=120000)
            body=await resp.body()
            if not body.startswith(b"PK"):
                raise RuntimeError("No se pudo obtener el XLSX científico desde OneDrive.")
            dest.write_bytes(body)
        await browser.close()
    if not dest.exists() or dest.stat().st_size<1000:
        raise RuntimeError("Descarga científica vacía o incompleta.")

def build(path:Path):
    wb=load_workbook(path,data_only=True,read_only=True)
    ws=wb[wb.sheetnames[0]]
    rows=list(ws.iter_rows(values_only=True))
    if not rows: raise RuntimeError("Excel científico vacío.")
    events=[]; variable=[]; undated=[]; issues=[]
    for idx,row in enumerate(rows[1:],start=2):
        if len(row)<6: continue
        day,month_raw,year,name,desc,cat=row[:6]
        name=norm(name)
        if not name: continue
        month=MONTHS.get(norm(month_raw))
        yr=int(year) if isinstance(year,(int,float)) else None
        common={"id":f"sci-{idx-1}","name":name,"description":norm(desc),"category":norm(cat),"year":yr,"source_row":idx}
        if isinstance(day,(int,float)) and month:
            events.append({**common,"day":int(day),"month":month})
        elif isinstance(day,str) and month and not re.match(r"^\d{4}-\d{2}-\d{2}",day):
            variable.append({**common,"month":month,"date_text":day.strip()})
        else:
            if hasattr(day,"date") and month:
                issues.append({"source_row":idx,"name":name,"issue":f"Campo Día contiene {day.date().isoformat()} mientras Mes={norm(month_raw)}"})
            undated.append({**common,"date_text":norm(day) or None,"month_text":norm(month_raw) or None})
    events.sort(key=lambda x:(x["month"],x["day"],x["name"].casefold()))
    return {"meta":{"title":"Efemérides científicas, académicas y culturales","source":SOURCE_URL,"records":len(events)+len(variable)+len(undated),"dated_records":len(events),"variable_date_records":len(variable),"undated_records":len(undated),"synced_from_onedrive":True},"events":events,"variable_events":variable,"undated_records":undated,"issues":issues}

async def main():
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        xlsx=Path(td)/"Efemerides_cientificas.xlsx"
        await download(xlsx)
        payload=build(xlsx)
    current=None
    if OUTPUT.exists():
        try: current=json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception: pass
    if current and current.get("events")==payload.get("events") and current.get("variable_events")==payload.get("variable_events") and current.get("undated_records")==payload.get("undated_records"):
        print("Sin cambios en efemérides científicas.")
        return
    payload["meta"]["last_sync_utc"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Actualizado {OUTPUT}: {payload['meta']['records']} registros.")

if __name__=="__main__":
    asyncio.run(main())
