import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.services.database import engine

from ..models import Customers, CustomerTypes

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerAddOrEdit(BaseModel):
    id: str
    type_id: int
    name: str


class CustomerTypeAdd(BaseModel):
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
    stmt = select(Customers).options(selectinload(Customers.type))
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

    customers = [
        {
            "id": row.id,
            "name": row.name,
            "type": row.type.name,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
    return {"customers": customers, "total": total, "page": page}


@router.post("/customer")
def add_customer(session: SessionDep, body: CustomerAddOrEdit):
    existing_user = session.get(Customers, body.id)

    if existing_user is not None:
        raise HTTPException(status_code=404, detail=f"{body.id} already exists")

    existing_type = session.get(CustomerTypes, body.type_id)

    if existing_type is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find type with id {body.type_id}"
        )

    session.execute(
        insert(Customers).values(id=body.id, type_id=body.type_id, name=body.name)
    )
    session.commit()
    return {"success": f"added new customer {body.id}"}


@router.post("/customer-type")
def add_customer_type(session: SessionDep, body: CustomerTypeAdd):
    existing = session.execute(
        select(CustomerTypes).where(CustomerTypes.name == body.name)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail=f"{body.name} exists")
    session.execute(insert(CustomerTypes).values(name=body.name))
    session.commit()
    return {"success": f"added new customer type {body.name}"}


@router.put("/customer")
def edit_customer(session: SessionDep, body: CustomerAddOrEdit):
    existing_user = session.get(Customers, body.id)

    if existing_user is None:
        raise HTTPException(status_code=404, detail=f"{body.id} not found")

    existing_type = session.get(CustomerTypes, body.type_id)

    if existing_type is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find type with id {body.type_id}"
        )

    existing_user.name = body.name
    existing_user.updated_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"updated {body.id}"}


@router.put("/customer-type")
def edit_customer_type(session: SessionDep, body: EditCustomerType):
    existing_type = session.get(CustomerTypes, body.id)

    if existing_type is None:
        raise HTTPException(
            status_code=404, detail=f"Unable to find type with id {body.id}"
        )
    existing_type.name = body.name
    existing_type.updated_at = datetime.datetime.now().timestamp()
    session.commit()
    return {"success": f"updated type {body.id}"}
