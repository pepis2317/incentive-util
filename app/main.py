from fastapi import FastAPI

from .routers import customers, invoices, items, records, reports

app = FastAPI()

app.include_router(invoices.router)
app.include_router(records.router)
app.include_router(items.router)
app.include_router(customers.router)
app.include_router(reports.router)