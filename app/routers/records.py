import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import (
    DiscountRecords,
    DiscountRecordSnapshots,
    Invoices,
    InvoiceSnapshots,
    Items,
    TransactionDiscountSnapshots,
    TransactionRecords,
    TransactionRecordSnapshots,
)

router = APIRouter(prefix="/transaction-records", tags=["transaction-records"])


class DiscountEditRow(BaseModel):
    discount_record_id: int
    discount_type: str
    discount_value: Decimal


class AddDiscountRow(BaseModel):
    transaction_record_id: int
    discount_type: str
    discount_value: Decimal


class RecordEditRow(BaseModel):
    record_id: int
    price_snapshot: Decimal
    item_id: str
    quantity: int


class ItemDiscount(BaseModel):
    discount_type: str
    discount_value: Decimal
    discount_step: int


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def apply_discount(record: TransactionRecords):
    discounts = sorted(record.discount_records, key=lambda d: d.step)
    discounted_price = record.price_snapshot
    for discount in discounts:
        if discount.type == "percentage":
            discounted_price -= discounted_price * (discount.value / 100)
        elif discount.type == "flat":
            discounted_price -= discount.value
    return discounted_price


@router.put("/edit-transaction-record")
def edit_transaction_record(session: SessionDep, body: RecordEditRow):
    record = session.get(
        TransactionRecords,
        body.record_id,
        options=[
            selectinload(TransactionRecords.invoice).selectinload(
                Invoices.transaction_records
            )
        ],
    )

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

    invoice_snapshot_id = session.execute(
        insert(InvoiceSnapshots)
        .values(
            invoice_id=record.invoice_id,
            transaction_id=record.invoice.transaction_id,
            customer_id=record.invoice.customer_id,
        )
        .returning(InvoiceSnapshots.id)
    ).scalar_one()

    transaction_record_snapshots = [
        {
            "invoice_snapshot_id": invoice_snapshot_id,
            "item_id": rec.item_id,
            "quantity": rec.quantity,
            "undiscounted_price": rec.price_snapshot,
            "discounted_price": apply_discount(rec),
        }
        for rec in record.invoice.transaction_records
    ]

    session.execute(
        insert(TransactionRecordSnapshots).values(transaction_record_snapshots)
    )

    record.quantity = body.quantity
    record.item_id = body.item_id
    record.price_snapshot = body.price_snapshot
    record.updated_at = datetime.datetime.now().timestamp()

    session.commit()

    return {"success": f"transaction record {body.record_id} has been updated"}


@router.put("/add-discount-record")
def add_discount_record(session: SessionDep, body: AddDiscountRow):
    record = session.get(
        TransactionRecords,
        body.transaction_record_id,
        options=[selectinload(TransactionRecords.discount_records)],
    )

    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    transaction_discount_snapshot_id = session.execute(
        insert(TransactionDiscountSnapshots)
        .values(transaction_record_id=body.transaction_record_id)
        .returning(TransactionDiscountSnapshots.id)
    ).scalar_one()

    discount_record_snapshots = [
        {
            "transaction_discount_snapshot_id": transaction_discount_snapshot_id,
            "step": discount.step,
            "value": discount.value,
            "type": discount.type,
        }
        for discount in record.discount_records
    ]

    session.execute(insert(DiscountRecordSnapshots).values(discount_record_snapshots))

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
    record = session.get(
        DiscountRecords,
        body.discount_record_id,
        options=[
            selectinload(DiscountRecords.transaction_record).selectinload(
                TransactionRecords.discount_records
            )
        ],
    )

    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find record {body.record_id}"
        )

    transaction_discount_snapshot_id = session.execute(
        insert(TransactionDiscountSnapshots)
        .values(transaction_record_id=record.transaction_record_id)
        .returning(TransactionDiscountSnapshots.id)
    ).scalar_one()

    discount_record_snapshots = [
        {
            "transaction_discount_snapshot_id": transaction_discount_snapshot_id,
            "step": discount.step,
            "value": discount.value,
            "type": discount.type,
        }
        for discount in record.transaction_record.discount_records
    ]

    session.execute(insert(DiscountRecordSnapshots).values(discount_record_snapshots))

    record.type = body.discount_type
    record.value = body.discount_value
    record.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"discount record {body.discount_record_id} has been updated"}


@router.delete("/delete-transaction-record")
def delete_transaction_record_row(session: SessionDep, id: int):
    record = session.get(
        TransactionRecords,
        id,
        options=[
            selectinload(TransactionRecords.invoice).selectinload(
                Invoices.transaction_records
            )
        ],
    )

    if record is None:
        raise HTTPException(status_code=404, detail=f"Unable to find record {id}")

    invoice_snapshot_id = session.execute(
        insert(InvoiceSnapshots)
        .values(
            invoice_id=record.invoice_id,
            transaction_id=record.invoice.transaction_id,
            customer_id=record.invoice.customer_id,
        )
        .returning(InvoiceSnapshots.id)
    ).scalar_one()

    transaction_record_snapshots = [
        {
            "invoice_snapshot_id": invoice_snapshot_id,
            "item_id": record.item_id,
            "quantity": record.quantity,
            "undiscounted_price": record.price_snapshot,
            "discounted_price": apply_discount(record),
        }
        for record in record.invoice.transaction_records
    ]

    session.execute(
        insert(TransactionRecordSnapshots).values(transaction_record_snapshots)
    )

    session.delete(record)
    session.commit()

    return {"success": f"transaction record {id} has been deleted"}


@router.delete("/delete-discount-record")
def delete_discount_record_row(session: SessionDep, id: int):
    record = session.get(
        DiscountRecords,
        id,
        options=[
            selectinload(DiscountRecords.transaction_record).selectinload(
                TransactionRecords.discount_records
            )
        ],
    )
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unable to find record {id}")

    transaction_discount_snapshot_id = session.execute(
        insert(TransactionDiscountSnapshots)
        .values(transaction_record_id=record.transaction_record_id)
        .returning(TransactionDiscountSnapshots.id)
    ).scalar_one()

    discount_record_snapshots = [
        {
            "transaction_discount_snapshot_id": transaction_discount_snapshot_id,
            "step": discount.step,
            "value": discount.value,
            "type": discount.type,
        }
        for discount in record.transaction_record.discount_records
    ]

    session.execute(insert(DiscountRecordSnapshots).values(discount_record_snapshots))

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
