import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import (
    DiscountRecords,
    DiscountRecordSnapshots,
    Invoices,
    InvoiceSnapshots,
    Items,
    TransactionRecords,
    TransactionRecordSnapshots,
)

router = APIRouter(prefix="/transaction-records", tags=["transaction-records"])


class DiscountEditRow(BaseModel):
    discount_record_id: int
    discount_type: str
    discount_value: Decimal


class AddDiscountRow(BaseModel):
    discount_type: str
    discount_value: Decimal


class RecordEditRow(BaseModel):
    record_id: int
    price_snapshot: Decimal
    item_id: str
    quantity: int
    discounts: list[DiscountEditRow]
    discounts_to_delete: list[int]
    discounts_to_add: list[AddDiscountRow]


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
            ),
            selectinload(TransactionRecords.discount_records),
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

    other_item_ids = {
        r.item_id for r in record.invoice.transaction_records if r.id != record.id
    }

    if body.item_id in other_item_ids:
        raise HTTPException(
            status_code=400,
            detail="Item already exists in this invoice",
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
            "price_snapshot": rec.price_snapshot,
        }
        for rec in record.invoice.transaction_records
    ]

    inserted_tr_snapshots = (
        session.execute(
            insert(TransactionRecordSnapshots)
            .values(transaction_record_snapshots)
            .returning(TransactionRecordSnapshots)
        )
        .scalars()
        .all()
    )

    item_discount_map = {
        transaction.item_id: transaction.discount_records
        for transaction in record.invoice.transaction_records
    }

    discount_record_snapshots = []
    for snapshot in inserted_tr_snapshots:
        discounts = item_discount_map[snapshot.item_id]
        for discount in discounts:
            discount_record_snapshots.append(
                {
                    "transaction_record_snapshot_id": snapshot.id,
                    "step": discount.step,
                    "value": discount.value,
                    "type": discount.type,
                }
            )
    if discount_record_snapshots:
        session.execute(
            insert(DiscountRecordSnapshots).values(discount_record_snapshots)
        )

    record.quantity = body.quantity
    record.item_id = body.item_id
    record.price_snapshot = body.price_snapshot
    record.updated_at = datetime.datetime.now().timestamp()
    record.invoice.updated_at = datetime.datetime.now().timestamp()

    discounts_by_id = {d.id: d for d in record.discount_records}

    for discount_id in body.discounts_to_delete:
        discount = discounts_by_id.pop(discount_id, None)
        if discount is None:
            raise HTTPException(404, f"discount {discount_id} not found on this record")
        session.delete(discount)

    session.flush()
    for row in body.discounts:
        discount = discounts_by_id.get(row.discount_record_id)
        if discount is None:
            raise HTTPException(
                404, f"discount {row.discount_record_id} not found on this record"
            )
        discount.type = row.discount_type
        discount.value = row.discount_value
        discount.updated_at = datetime.datetime.now().timestamp()

    sorted_discounts = sorted(discounts_by_id.values(), key=lambda d: d.step)
    for new_step, discount in enumerate(sorted_discounts, start=1):
        discount.step = new_step

    latest_step = session.execute(
        select(func.coalesce(func.max(DiscountRecords.step), 0)).where(
            DiscountRecords.transaction_record_id == body.record_id
        )
    ).scalar_one()

    discounts_to_insert = [
        {
            "transaction_record_id": body.record_id,
            "step": latest_step + step,
            "value": discount.discount_value,
            "type": discount.discount_type,
        }
        for step, discount in enumerate(body.discounts_to_add, start=1)
    ]

    if discounts_to_insert:
        session.execute(insert(DiscountRecords).values(discounts_to_insert))

    session.commit()

    return {"success": f"transaction record {body.record_id} has been updated"}


@router.delete("/")
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
            "price_snapshot": record.price_snapshot,
        }
        for record in record.invoice.transaction_records
    ]

    inserted_tr_snapshots = (
        session.execute(
            insert(TransactionRecordSnapshots)
            .values(transaction_record_snapshots)
            .returning(TransactionRecordSnapshots)
        )
        .scalars()
        .all()
    )

    item_discount_map = {
        transaction.item_id: transaction.discount_records
        for transaction in record.invoice.transaction_records
    }

    discount_record_snapshots = []
    for snapshot in inserted_tr_snapshots:
        discounts = item_discount_map[snapshot.item_id]
        for discount in discounts:
            discount_record_snapshots.append(
                {
                    "transaction_record_snapshot_id": snapshot.id,
                    "step": discount.step,
                    "value": discount.value,
                    "type": discount.type,
                }
            )
    if discount_record_snapshots:
        session.execute(
            insert(DiscountRecordSnapshots).values(discount_record_snapshots)
        )

    session.delete(record)
    session.commit()

    return {"success": f"transaction record {id} has been deleted"}
