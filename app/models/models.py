import decimal
from typing import Optional

from sqlalchemy import ForeignKey, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CustomerTypes(Base):
    __tablename__ = "customer_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    customers: Mapped[list["Customers"]] = relationship(
        "Customers", back_populates="type"
    )


class Items(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    base_price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    sell_price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    discounts: Mapped[list["Discounts"]] = relationship(
        "Discounts", back_populates="item"
    )
    transaction_records: Mapped[list["TransactionRecords"]] = relationship(
        "TransactionRecords", back_populates="item"
    )


class Customers(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("customer_types.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    type: Mapped["CustomerTypes"] = relationship(
        "CustomerTypes", back_populates="customers"
    )
    discounts: Mapped[list["Discounts"]] = relationship(
        "Discounts", back_populates="customer"
    )
    invoices: Mapped[list["Invoices"]] = relationship(
        "Invoices", back_populates="customer"
    )


class Discounts(Base):
    __tablename__ = "discounts"

    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), primary_key=True)
    step: Mapped[int] = mapped_column(
        Integer, primary_key=True, server_default=text("1")
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    customer: Mapped["Customers"] = relationship(
        "Customers", back_populates="discounts"
    )
    item: Mapped["Items"] = relationship("Items", back_populates="discounts")


class Invoices(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    customer: Mapped["Customers"] = relationship("Customers", back_populates="invoices")
    transaction_records: Mapped[list["TransactionRecords"]] = relationship(
        "TransactionRecords", back_populates="invoice"
    )


class TransactionRecords(Base):
    __tablename__ = "transaction_records"
    __table_args__ = (UniqueConstraint("invoice_id", "item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    invoice: Mapped["Invoices"] = relationship(
        "Invoices", back_populates="transaction_records"
    )
    item: Mapped["Items"] = relationship("Items", back_populates="transaction_records")
    discount_records: Mapped[list["DiscountRecords"]] = relationship(
        "DiscountRecords",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="transaction_record",
    )


class DiscountRecords(Base):
    __tablename__ = "discount_records"
    __table_args__ = (UniqueConstraint("transaction_record_id", "step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_record_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_records.id", ondelete="CASCADE"), nullable=False,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    transaction_record: Mapped["TransactionRecords"] = relationship(
        "TransactionRecords", back_populates="discount_records"
    )
