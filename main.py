#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py (Versione di test)
--------------------------------
Questa versione minimale serve per verificare che la route "/" venga raggiunta e restituisca HTML.
"""

import os
import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.get("/", response_class=HTMLResponse)
async def index():
    logging.info("Accesso alla home page '/'")
    html = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
      <meta charset="UTF-8">
      <title>Gianky Coin Mini App - Test</title>
    </head>
    <body>
      <h1>Hello, World!</h1>
      <p>Questa è la home page della Gianky Coin Mini App.</p>
      <p><a href="/connect">Collega il tuo wallet</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
