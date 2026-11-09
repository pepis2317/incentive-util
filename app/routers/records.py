import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import (
    Customers,
    DiscountRecords,
    Invoices,
    Items,
    TransactionRecords,
)

router = APIRouter(prefix="/transaction-records", tags=["transaction-records"])


class ItemDiscount(BaseModel):
    discount_type: str
    discount_value: Decimal
    discount_step: int


class RecordAddItem(BaseModel):
    item_id: str
    item_quantity: int
    discounts: list[ItemDiscount]


class DiscountEditRow(BaseModel):
    discount_record_id: int
    discount_type: str
    discount_value: Decimal


class AddDiscountRow(BaseModel):
    transaction_record_id: int
    discount_type: str
    discount_value: Decimal


class RecordAdd(BaseModel):
    customer_id: str
    transaction_id: str
    items: list[RecordAddItem]


class RecordEditRow(BaseModel):
    record_id: int
    item_id: str
    quantity: int


class EditRecordAddItem(BaseModel):
    invoice_id: int
    item_id: str
    quantity: int
    discounts: list[ItemDiscount]


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

def calculate_discounted_price(sell_price:Decimal, discounts:DiscountRecords):
    sorted_discounts = sorted(discounts, key=lambda d: d.step)
    result = sell_price
    for discount in sorted_discounts:
        if discount.type == "percentage":
            result -= result * (discount.value/100)
        elif discount.type == "flat":
            result -= discount.value
    return result

@router.get("/")
def list_transaction_records(
    session: SessionDep,
    transaction_id: str,
    item_query: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = (
        select(TransactionRecords)
        .options(
            selectinload(TransactionRecords.invoice),
            selectinload(TransactionRecords.discount_records),
            selectinload(TransactionRecords.item),
        )
        .where(
            TransactionRecords.invoice.has(Invoices.transaction_id == transaction_id)
        )
    )

    if item_query:
        stmt = stmt.where(
            TransactionRecords.item.has(
                or_(
                    Items.id.contains(item_query, autoescape=True),
                    Items.name.contains(item_query, autoescape=True),
                )
            )
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    rows = session.scalars(
        stmt.order_by(TransactionRecords.created_at.asc(), TransactionRecords.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    records = [
        {
            "id": q.id,
            "item": q.item,
            "quantity": q.quantity,
            "discounts": sorted(q.discount_records, key=lambda d: d.step),
            "undiscounted_total": q.item.sell_price * q.quantity,
            "discounted_total": calculate_discounted_price(q.item.sell_price, q.discount_records) * q.quantity,
            "created_at": q.created_at,
            "updated_at": q.updated_at,
        }
        for q in rows
    ]

    return {"records": records, "total": total, "page": page}


@router.post("/")
def add_transaction_records(session: SessionDep, body: RecordAdd):
    existing = session.execute(
        select(Invoices).where(Invoices.transaction_id == body.transaction_id)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400, detail=f"invoice with id {body.transaction_id} exists"
        )

    seen_item_ids = set()
    for item in body.items:
        if item.item_id in seen_item_ids:
            raise HTTPException(
                status_code=400, detail=f"duplicate item id {item.item_id}"
            )
        seen_item_ids.add(item.item_id)

    customer_exists = session.execute(
        select(Customers).where(Customers.id == body.customer_id)
    ).scalar_one_or_none()

    if customer_exists is None:
        raise HTTPException(
            status_code=400,
            detail=f"customer {body.customer_id} does not exist",
        )

    item_ids = {entry.item_id for entry in body.items}

    found_ids = set(
        session.execute(select(Items.id).where(Items.id.in_(item_ids))).scalars().all()
    )

    missing = item_ids - found_ids

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"items not found: {sorted(missing)}",
        )

    seen = set()
    for item in body.items:
        for discount in item.discounts:
            key = (item.item_id, discount.discount_step)

            if key in seen:
                raise HTTPException(
                    status_code=404,
                    detail=f"found duplicate discount step: {key}",
                )

            if discount.discount_step > 1:
                prev_key = (item.item_id, discount.discount_step - 1)
                if prev_key not in seen:
                    raise HTTPException(
                        status_code=404,
                        detail=f"discount steps must be sequential: {key}",
                    )
            elif discount.discount_step < 1:
                raise HTTPException(
                    status_code=404,
                    detail=f"discount steps must start from 1: {key}",
                )

            seen.add(key)

    invoice_id = session.execute(
        insert(Invoices)
        .values(transaction_id=body.transaction_id, customer_id=body.customer_id)
        .returning(Invoices.id)
    ).scalar_one()

    transaction_records_to_insert = [
        {
            "invoice_id": invoice_id,
            "item_id": item.item_id,
            "quantity": item.item_quantity,
        }
        for item in body.items
    ]

    transaction_record_ids = session.execute(
        insert(TransactionRecords)
        .values(transaction_records_to_insert)
        .returning(TransactionRecords.id, TransactionRecords.item_id)
    )

    item_to_record_id = {row.item_id: row.id for row in transaction_record_ids}

    discounts_to_insert = [
        {
            "transaction_record_id": item_to_record_id[item.item_id],
            "step": discount.discount_step,
            "value": discount.discount_value,
            "type": discount.discount_type,
        }
        for item in body.items
        for discount in item.discounts
    ]

    session.execute(insert(DiscountRecords).values(discounts_to_insert))

    session.commit()
    return {"success": "price records added"}


@router.put("/edit-transaction-record")
def edit_transaction_record(session: SessionDep, body: RecordEditRow):
    record = session.get(TransactionRecords, body.record_id)

    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    item_exists = session.execute(
        select(Items).where(Items.id == body.item_id)
    ).scalar_one_or_none()

    if item_exists is None:
        raise HTTPException(
            status_code=400,
            detail=f"Item {body.item_id} does not exist",
        )

    record.quantity = body.quantity
    record.item_id = body.item_id
    record.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"transaction record {body.record_id} has been updated"}


@router.put("/add-discount-record")
def add_discount_record(session: SessionDep, body: AddDiscountRow):
    record = session.get(TransactionRecords, body.transaction_record_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    latest_step = session.execute(
        select(func.max(DiscountRecords.step)).where(
            DiscountRecords.transaction_record_id == body.transaction_record_id
        )
    ).scalar()

    session.execute(
        insert(DiscountRecords).values(
            transaction_record_id=body.transaction_record_id,
            step=latest_step + 1,
            type=body.discount_type,
            value=body.discount_value,
        )
    )

    session.commit()
    return {"success": f"added discount record for {body.transaction_record_id}"}


@router.put("/edit-discount-record")
def edit_discount_record(session: SessionDep, body: DiscountEditRow):
    record = session.get(DiscountRecords, body.discount_record_id)

    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    record.type = body.discount_type
    record.value = body.discount_value
    record.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"discount record {body.discount_record_id} has been updated"}


@router.put("/add-transaction-record-item")
def add_transaction_record_item(session: SessionDep, body: EditRecordAddItem):
    records = (
        session.execute(
            select(TransactionRecords).where(
                TransactionRecords.invoice_id == body.invoice_id
            )
        )
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
        select(Items).where(Items.id == body.item_id)
    ).scalar_one_or_none()

    if item_exists == None:
        raise HTTPException(
            status_code=400,
            detail=f"Item {body.item_id} does not exist",
        )

    seen = set()
    for discount in body.discounts:
        key = discount.discount_step

        if key in seen:
            raise HTTPException(
                status_code=404,
                detail=f"found duplicate discount step: {key}",
            )

        if discount.discount_step > 1:
            prev_key = discount.discount_step - 1
            if prev_key not in seen:
                raise HTTPException(
                    status_code=404,
                    detail=f"discount steps must be sequential: {key}",
                )
        elif discount.discount_step < 1:
            raise HTTPException(
                status_code=404,
                detail=f"discount steps must start from 1: {key}",
            )

        seen.add(key)

    transaction_record_id = session.execute(
        insert(TransactionRecords)
        .values(
            invoice_id=body.invoice_id, item_id=body.item_id, quantity=body.quantity
        )
        .returning(TransactionRecords.id)
    ).scalar_one()

    discounts_to_insert = [
        {
            "transaction_record_id": transaction_record_id,
            "step": discount.discount_step,
            "value": discount.discount_value,
            "type": discount.discount_type,
        }
        for discount in body.discounts
    ]

    session.execute(insert(DiscountRecords).values(discounts_to_insert))

    session.commit()

    return {"success": f"added new record for invoice {body.invoice_id}"}


@router.delete("/delete-transaction-record")
def delete_transaction_record_row(session: SessionDep, id: int):
    record = session.get(TransactionRecords, id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unable to find record {id}")
    session.delete(record)
    session.commit()

    return {"success": f"transaction record {id} has been deleted"}


@router.delete("/delete-discount-record")
def delete_discount_record_row(session: SessionDep, id: int):
    record = session.get(DiscountRecords, id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unable to find record {id}")

    session.delete(record)
    session.flush()

    discounts_after = (
        session.execute(
            select(DiscountRecords).where(
                DiscountRecords.transaction_record_id == record.transaction_record_id,
                DiscountRecords.step > record.step,
            )
        )
        .scalars()
        .all()
    )

    for discounts in discounts_after:
        discounts.step -= 1

    session.commit()

    return {"success": f"discount record {id} has been deleted"}
