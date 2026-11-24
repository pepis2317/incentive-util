import datetime
from collections import OrderedDict
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from app.services.database import engine

from ..models import Items

router = APIRouter(prefix="/items", tags=["items"])


class ItemEditOrAdd(BaseModel):
    id: str
    name: str
    type: str
    brand: str
    unit: str
    base_price: Decimal
    sell_price: Decimal


class ItemsCacheQuery(BaseModel):
    model_config = ConfigDict(frozen=True)
    item_query: str
    page: int
    page_size: int


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

MAX_CACHE_SIZE = 100
items_cache: OrderedDict[ItemsCacheQuery, dict] = OrderedDict()


def update_items_cache(query: ItemsCacheQuery, items: list[Items], total: int):
    if len(items_cache) >= MAX_CACHE_SIZE:
        items_cache.popitem(last=False)
    items_cache[query] = {"items": items, "total": total}


def get_items_cache(query: ItemsCacheQuery):
    cached = items_cache.get(query)
    if cached is None:
        return None
    items_cache.move_to_end(query)
    return {"items": cached["items"], "total": cached["total"], "page": query.page}


@router.get("/")
def list_items(
    session: SessionDep,
    item_query: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    query = ItemsCacheQuery(item_query=item_query, page=page, page_size=page_size)
    cached = get_items_cache(query)
    if cached is not None:
        return cached

    stmt = select(Items)
    if item_query:
        stmt = stmt.where(
            or_(
                Items.id.icontains(item_query, autoescape=True),
                Items.name.icontains(item_query, autoescape=True),
            )
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))

    items = session.scalars(
        stmt.order_by(Items.created_at.desc(), Items.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    update_items_cache(query, items, total)

    return {"items": items, "total": total, "page": page}


@router.put("/")
def edit_item(session: SessionDep, body: ItemEditOrAdd):
    item = session.get(Items, body.id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unable to find item {id}")
    item.name = body.name
    item.type = body.type
    item.brand = body.brand
    item.unit = body.unit
    item.base_price = body.base_price
    item.sell_price = body.sell_price
    item.updated_at = datetime.datetime.now().timestamp()
    session.commit()
    
    items_cache.clear()
    return {"success": f"item {body.id} has been updated"}


@router.post("/")
def add_item(session: SessionDep, body: ItemEditOrAdd):
    existing = session.execute(
        select(Items).where(Items.id == body.id)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail=f"Items with id {body.id} exists")

    session.execute(
        insert(Items).values(
            id=body.id,
            name=body.name,
            type=body.type,
            brand=body.brand,
            unit=body.unit,
            base_price=body.base_price,
            sell_price=body.sell_price,
        )
    )
    session.commit()
    items_cache.clear()
    return {"success": f"added new item {body.id}"}


@router.delete("/")
def delete_item(session: SessionDep, id: int):
    item = session.get(Items, id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unable to find invoice {id}")
    session.delete(item)
    session.commit()

    items_cache.clear()
    return {"success": f"invoice {id} has been deleted"}
