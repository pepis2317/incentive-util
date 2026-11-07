import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.services.database import Base, engine

Item = Base.classes["items"]

router = APIRouter(prefix="/items", tags=["items"])


class ItemEditOrAdd(BaseModel):
    id: str
    name: str
    type: str
    brand: str
    unit: str
    base_price: Decimal
    sell_price: Decimal


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

OrderBy = Literal[
    "id",
    "name",
    "type",
    "brand",
    "unit",
    "base_price",
    "sell_price",
    "created_at",
    "updated_at",
]


@router.get("/")
def list_items(
    session: SessionDep,
    id_query: str | None = None,
    name_query: str | None = None,
    order_by: OrderBy = "created_at",
    descending: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    stmt = select(Item)
    if id_query:
        stmt = stmt.where(Item.id.contains(id_query, autoescape=True))
    if name_query:
        stmt = stmt.where(Item.name.contains(name_query, autoescape=True))

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    column = getattr(Item, order_by)
    items = session.scalars(
        stmt.order_by(column.desc() if descending else column.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {"items": items, "total": total, "page": page}


@router.put("/")
def edit_item(session: SessionDep, body: ItemEditOrAdd):
    item = session.get(Item, body.id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    item.name = body.name
    item.type = body.type
    item.brand = body.brand
    item.unit = body.unit
    item.base_price = body.base_price
    item.sell_price = body.sell_price
    item.updatted_at = datetime.datetime.now().timestamp()
    session.commit()

    return {"success": f"item {body.id} has been updated"}


@router.post("/")
def add_item(session: SessionDep, body: ItemEditOrAdd):
    existing = session.execute(
        select(Item).where(Item.id == body.id)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400, detail=f"Item with id {body.id} exists"
        )

    session.execute(
        insert(Item).values(
            id=body.id,
            name=body.name,
            type=body.type,
            brand=body.brand,
            unit=body.unit,
            base_price=body.base_price,
            sell_price=body.sell_price
        )
    )
    session.commit()
    return {"success": f"added new item {body.id}"}
    

@router.delete("/")
def delete_item(session: SessionDep, id: int):
    item = session.get(Item, id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    session.delete(item)
    session.commit()

    return {"success": f"invoice {id} has been deleted"}
