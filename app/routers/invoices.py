import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.database import engine

from ..models import Invoices

router = APIRouter(prefix="/invoices", tags=["invoices"])


class InvoiceEdit(BaseModel):
    id: int
    transaction_id: str


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

OrderBy = Literal["invoice_id", "created_at", "updated_at"]


@router.get("/")
def list_invoices(
    session: SessionDep,
    transaction_id_query: str | None = None,
    order_by: OrderBy = "created_at",
    descending: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = select(Invoices)
    if transaction_id_query:
        stmt = stmt.where(
            Invoices.transaction_id.contains(transaction_id_query, autoescape=True)
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    column = getattr(Invoices, order_by)
    invoices = session.scalars(
        stmt.order_by(column.desc() if descending else column.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

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
