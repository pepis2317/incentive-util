import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import Invoices, TransactionRecords

router = APIRouter(prefix="/reports", tags=["reports"])


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


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
        discounted_price = apply_discount(record)
        total += discounted_price * record.quantity
    return total


def calculate_undiscounted_total(transaction_records: list[TransactionRecords]):
    total = 0
    for record in transaction_records:
        total += record.price_snapshot * record.quantity
    return total


@router.get("/")
def get_home_data(session: SessionDep):
    now = datetime.datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + datetime.timedelta(days=32)).replace(day=1)

    start_of_this_month = start.timestamp()
    next_month_start = end.timestamp()

    invoices_stmt = (
        select(Invoices)
        .options(
            selectinload(Invoices.transaction_records).options(
                selectinload(TransactionRecords.discount_records)
            ),
            selectinload(Invoices.customer),
        )
        .where(
            Invoices.created_at >= start_of_this_month,
            Invoices.created_at < next_month_start,
        )
    )
    rows = session.scalars(
        invoices_stmt.order_by(Invoices.created_at.desc(), Invoices.id)
    ).all()

    sell_out_rows = []
    sell_in_rows = []
    for r in rows:
        if r.type == "sell_out":
            sell_out_rows.append(r)
        else:
            sell_in_rows.append(r)

    total_sell_out_amount = 0

    for row in sell_out_rows:
        total_sell_out_amount += calculate_discounted_total(row.transaction_records)

    total_sell_in_amount = 0

    for row in sell_in_rows:
        total_sell_in_amount += calculate_discounted_total(row.transaction_records)

    return {
        "total_sell_out_amount": total_sell_out_amount,
        "total_sell_in_amount": total_sell_in_amount,
    }
