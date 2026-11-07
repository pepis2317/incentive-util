from fastapi import FastAPI

from .routers import invoices, items, records

app = FastAPI()

app.include_router(invoices.router)
app.include_router(records.router)
app.include_router(items.router)