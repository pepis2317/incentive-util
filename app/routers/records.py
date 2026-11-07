import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import Base, engine

Record = Base.classes["price_records"]
Invoice = Base.classes["invoices"]
Item = Base.classes["items"]

router = APIRouter(prefix="/price-records", tags=["price-records"])


class ItemPrice(BaseModel):
    item_id: str
    price: Decimal


class RecordAdd(BaseModel):
    transaction_id: str
    item_prices: list[ItemPrice]


class RecordEditRow(BaseModel):
    record_id: int
    item_id: str
    price: Decimal


class RecordAddRow(BaseModel):
    invoice_id: int
    item_id: str
    price: Decimal


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

OrderBy = Literal["item_id", "transaction_id", "price", "created_at", "updated_at"]

ORDER_COLUMNS = {
    "item_id": Item.id,
    "transaction_id": Invoice.transaction_id,
    "price": Record.price,
    "created_at": Record.created_at,
    "updated_at": Record.updated_at,
}


@router.get("/")
def list_price_records(
    session: SessionDep,
    transaction_id_query: str | None = None,
    item_id_query: str | None = None,
    order_by: OrderBy = "created_at",
    descending: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = select(Record).options(
        selectinload(Record.items), selectinload(Record.invoices)
    )
    if transaction_id_query:
        stmt = stmt.where(
            Record.invoices.has(
                Invoice.transaction_id.contains(transaction_id_query, autoescape=True)
            )
        )

    if item_id_query:
        stmt = stmt.where(
            Record.items.has(Item.id.contains(item_id_query, autoescape=True))
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    if order_by == "item_id":
        stmt = stmt.outerjoin(Record.items)
    elif order_by == "transaction_id":
        stmt = stmt.outerjoin(Record.invoices)

    column = ORDER_COLUMNS[order_by]
    rows = session.scalars(
        stmt.order_by(column.desc() if descending else column.asc(), Record.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    records = [
        {
            "id": q.id,
            "item": q.items,
            "invoice": q.invoices,
            "pricecreated_at": q.created_at,
            "updated_at": q.updated_at,
        }
        for q in rows
    ]

    return {"records": records, "total": total, "page": page}


@router.post("/")
def add_price_records(session: SessionDep, body: RecordAdd):
    existing = session.execute(
        select(Invoice).where(Invoice.transaction_id == body.transaction_id)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400, detail=f"Invoice with id {body.transaction_id} exists"
        )
    item_ids = {entry.item_id for entry in body.item_prices}

    found_ids = set(
        session.execute(select(Item.id).where(Item.id.in_(item_ids))).scalars().all()
    )

    missing = item_ids - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"items not found: {sorted(missing)}",
        )

    invoice_id = session.execute(
        insert(Invoice).values(transaction_id=body.transaction_id).returning(Invoice.id)
    ).scalar_one()

    to_insert = [
        {
            "invoice_id": invoice_id,
            "price": item_price.price,
            "item_id": item_price.item_id,
        }
        for item_price in body.item_prices
    ]

    if to_insert:
        session.execute(insert(Record), to_insert)

    session.commit()
    return {"success": "price records added"}


@router.put("/edit")
def edit_price_record_row(session: SessionDep, body: RecordEditRow):
    record = session.get(Record, body.record_id)

    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    item_exists = session.execute(
        select(Item).where(Item.id == body.item_id)
    ).scalar_one_or_none()

    if item_exists == None:
        raise HTTPException(
            status_code=400,
            detail=f"Item {body.item_id} does not exist",
        )

    record.price = body.price
    record.item_id = body.item_id
    record.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"record {body.record_id} has been updated"}


@router.put("/add")
def add_price_record_row(session: SessionDep, body: RecordAddRow):
    records = (
        session.execute(select(Record).where(Record.invoice_id == body.invoice_id))
        .scalars()
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to find any record for invoice {body.invoice_id}",
        )

    invoice_item_ids = {record.item_id for record in records}
    if body.item_id in invoice_item_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice already has item {body.item_id}",
        )

    item_exists = session.execute(
        select(Item).where(Item.id == body.item_id)
    ).scalar_one_or_none()

    if item_exists == None:
        raise HTTPException(
            status_code=400,
            detail=f"Item {body.item_id} does not exist",
        )

    session.execute(
        insert(Record).values(
            item_id=body.item_id, price=body.price, invoice_id=body.invoice_id
        )
    )
    session.commit()

    return {"success": f"added new record for {body.invoice_id}"}


@router.delete("/")
def delete_price_record_row(session: SessionDep, id: int):
    record = session.get(Record, id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unable to find record {id}")
    session.delete(record)
    session.commit()

    return {"success": f"record {id} has been deleted"}
