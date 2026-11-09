import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import Invoices, TransactionRecords

router = APIRouter(prefix="/invoices", tags=["invoices"])


class InvoiceEdit(BaseModel):
    id: int
    transaction_id: str


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

def calculate_undiscounted_total(transaction_records: list[TransactionRecords]):
    total = 0
    for record in transaction_records:
        total += record.item.sell_price * record.quantity
    return total

def calculate_discounted_total(transaction_records: list[TransactionRecords]):
    total = 0
    for record in transaction_records:
        discounts = record.discount_records
        discounted_price = record.item.sell_price
        for discount in discounts:
            if discount.type == "percentage":
                discounted_price -= discounted_price * (discount.value / 100)
            elif discount.type == "flat":
                discounted_price -= discount.value
        total += discounted_price * record.quantity
    return total
            

@router.get("/")
def list_invoices(
    session: SessionDep,
    transaction_id_query: str | None = None,
    descending: bool = False,
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
            "transaction_id":row.transaction_id,
            "customer_name":row.customer.name,
            "undiscounted_total": calculate_undiscounted_total(row.transaction_records),
            "discounted_total": calculate_discounted_total(row.transaction_records),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]

    return {"invoices": invoices, "total": total, "page": page}


@router.put("/")
def edit_invoice(session: SessionDep, body: InvoiceEdit):
    invoice = session.get(Invoices, body.id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    invoice.invoice_id = body.transaction_id
    invoice.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"invoice {body.id} has been updated"}


@router.delete("/")
def delete_invoice(session: SessionDep, id: int):
    invoice = session.get(Invoices, id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    session.delete(invoice)
    session.commit()

    return {"success": f"invoice {id} has been deleted"}
