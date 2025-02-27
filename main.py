#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py
--------------------------------
Questa mini app (basata su FastAPI) serve il file "index.html" dalla cartella "static".
Assicurati che la cartella "static" si trovi nella stessa directory di questo file
e che contenga un file chiamato esattamente "index.html".
"""

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # Costruisci il percorso assoluto al file index.html
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_file = os.path.join(base_dir, "static", "index.html")
    logging.info("Percorso di index.html: " + index_file)
    if not os.path.exists(index_file):
        logging.error("File index.html non trovato in " + index_file)
        raise HTTPException(status_code=404, detail="File index.html non trovato")
    return FileResponse(index_file, media_type="text/html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
