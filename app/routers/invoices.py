import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import (
    Customers,
    DiscountRecords,
    Invoices,
    InvoiceSnapshots,
    Items,
    TransactionDiscountSnapshots,
    TransactionRecords,
    TransactionRecordSnapshots,
)

router = APIRouter(prefix="/invoices", tags=["invoices"])


class InvoiceEdit(BaseModel):
    id: int
    transaction_id: str
    customer_id: str


class InvoiceAdd(BaseModel):
    customer_id: str
    transaction_id: str
    items: list[InvoiceAddItem]


class InvoiceAddItem(BaseModel):
    item_id: str
    item_quantity: int
    price_snapshot: int
    discounts: list[ItemDiscount]


class ItemDiscount(BaseModel):
    discount_type: str
    discount_value: Decimal
    discount_step: int


class EditInvoiceAddItem(BaseModel):
    invoice_id: int
    item_id: str
    price_snapshot: Decimal
    quantity: int
    discounts: list[ItemDiscount]


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def calculate_undiscounted_total(transaction_records: list[TransactionRecords]):
    total = 0
    for record in transaction_records:
        total += record.price_snapshot * record.quantity
    return total


def apply_discount(record: TransactionRecords):
    discounts = record.discount_records
    discounted_price = record.price_snapshot
    for discount in discounts:
        if discount.type == "percentage":
            discounted_price -= discounted_price * (discount.value / 100)
        elif discount.type == "flat":
            discounted_price -= discount.value
    return discounted_price


def calculate_discounted_total(transaction_records: list[TransactionRecords]):
    total = 0
    for record in transaction_records:
        discounts = record.discount_records
        discounted_price = apply_discount(discounts)
        total += discounted_price * record.quantity
    return total


@router.get("/")
def list_invoices(
    session: SessionDep,
    transaction_id_query: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = select(Invoices).options(
        selectinload(Invoices.transaction_records).options(
            selectinload(TransactionRecords.item),
            selectinload(TransactionRecords.discount_records),
        ),
        selectinload(Invoices.customer),
    )
    if transaction_id_query:
        stmt = stmt.where(
            Invoices.transaction_id.contains(transaction_id_query, autoescape=True)
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    rows = session.scalars(
        stmt.order_by(Invoices.created_at.desc(), Invoices.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    invoices = [
        {
            "id": row.id,
            "transaction_id": row.transaction_id,
            "customer_name": row.customer.name,
            "undiscounted_total": calculate_undiscounted_total(row.transaction_records),
            "discounted_total": calculate_discounted_total(row.transaction_records),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]

    return {"invoices": invoices, "total": total, "page": page}


@router.get("/id")
def get_invoice_detail(session: SessionDep, id: int, item_query: str | None = None):
    stmt = (
        select(Invoices)
        .where(Invoices.id == id)
        .options(
            selectinload(Invoices.transaction_records).options(
                selectinload(TransactionRecords.transaction_discount_snapshots).options(
                    selectinload(TransactionDiscountSnapshots.discount_record_snapshots)
                ),
                selectinload(TransactionRecords.discount_records),
            ),
            selectinload(Invoices.invoice_snapshots).options(
                selectinload(InvoiceSnapshots.transaction_record_snapshots)
            ),
        )
    )

    if item_query:
        stmt = stmt.where(
            Invoices.transaction_records.any(
                TransactionRecords.item.has(
                    or_(
                        Items.id.contains(item_query, autoescape=True),
                        Items.name.contains(item_query, autoescape=True),
                    )
                )
            )
        )

    invoice = session.execute(stmt).scalar_one_or_none()
    return {"invoice": invoice}


@router.post("/")
def create_invoice(session: SessionDep, body: InvoiceAdd):
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
            "price_snapshot": item.price_snapshot,
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
    return {"success": "invoice created"}


@router.put("/")
def edit_invoice(session: SessionDep, body: InvoiceEdit):
    invoice = session.get(
        Invoices,
        body.id,
        options=[
            selectinload(Invoices.transaction_records).selectinload(
                TransactionRecords.discount_records
            )
        ],
    )

    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")

    invoice_snapshot_id = session.execute(
        insert(InvoiceSnapshots)
        .values(
            invoice_id=body.id,
            transaction_id=body.transaction_id,
            customer_id=body.customer_id,
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
        for record in invoice.transaction_records
    ]

    session.execute(
        insert(TransactionRecordSnapshots).values(transaction_record_snapshots)
    )

    invoice.transaction_id = body.transaction_id
    invoice.customer_id = body.customer_id
    invoice.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"invoice {body.id} has been updated"}


@router.put("/add-transaction-record-item")
def add_transaction_record_item(session: SessionDep, body: EditInvoiceAddItem):
    invoice = session.get(
        Invoices, body.invoice_id, options=[selectinload(Invoices.transaction_records)]
    )

    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")

    records = invoice.transaction_records

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

    invoice_snapshot_id = session.execute(
        insert(InvoiceSnapshots)
        .values(
            invoice_id=body.invoice_id,
            transaction_id=invoice.transaction_id,
            customer_id=invoice.customer_id,
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
        for record in records
    ]

    session.execute(
        insert(TransactionRecordSnapshots).values(transaction_record_snapshots)
    )

    transaction_record_id = session.execute(
        insert(TransactionRecords)
        .values(
            invoice_id=body.invoice_id,
            item_id=body.item_id,
            quantity=body.quantity,
            price_snapshot=body.price_snapshot,
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


@router.delete("/")
def delete_invoice(session: SessionDep, id: int):
    invoice = session.get(Invoices, id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    session.delete(invoice)
    session.commit()

    return {"success": f"invoice {id} has been deleted"}
