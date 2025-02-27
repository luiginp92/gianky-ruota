from fastapi import FastAPI
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.on_event("startup")
async def startup_event():
    logging.info("FastAPI startup event triggered.")

@app.get("/")
async def read_root():
    logging.info("Root endpoint '/' called.")
    return {"message": "Hello, World!"}
