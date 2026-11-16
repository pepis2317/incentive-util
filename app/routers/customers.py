import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from app.services.database import engine

from ..models import Customers

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerAddOrEdit(BaseModel):
    id: str
    name: str


class EditCustomerType(BaseModel):
    id: int
    name: str


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/")
def list_customers(
    session: SessionDep,
    customer_query: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = select(Customers)
    if customer_query:
        stmt = stmt.where(
            or_(
                Customers.id.icontains(customer_query, autoescape=True),
                Customers.name.icontains(customer_query, autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    rows = session.scalars(
        stmt.order_by(Customers.created_at.desc(), Customers.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {"customers": rows, "total": total, "page": page}


@router.post("/")
def add_customer(session: SessionDep, body: CustomerAddOrEdit):
    existing_user = session.get(Customers, body.id)

    if existing_user is not None:
        raise HTTPException(status_code=404, detail=f"{body.id} already exists")

    session.execute(insert(Customers).values(id=body.id, name=body.name))
    session.commit()
    return {"success": f"added new customer {body.id}"}


@router.put("/")
def edit_customer(session: SessionDep, body: CustomerAddOrEdit):
    existing_user = session.get(Customers, body.id)

    if existing_user is None:
        raise HTTPException(status_code=404, detail=f"{body.id} not found")

    existing_user.name = body.name
    existing_user.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"updated {body.id}"}
