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
    transaction_record_deletions: Mapped[list["TransactionRecordDeletions"]] = (
        relationship(
            "TransactionRecordDeletions",
            cascade="all, delete-orphan",
            passive_deletes=True,
            back_populates="invoice",
        )
    )
    transaction_records: Mapped[list["TransactionRecords"]] = relationship(
        "TransactionRecords",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="invoice",
    )


class TransactionRecordDeletions(Base):
    __tablename__ = "transaction_record_deletions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_snapshot: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )

    invoice: Mapped["Invoices"] = relationship(
        "Invoices", back_populates="transaction_record_deletions"
    )


class TransactionRecords(Base):
    __tablename__ = "transaction_records"
    __table_args__ = (UniqueConstraint("invoice_id", "item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_snapshot: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )
    updated_at: Mapped[Optional[int]] = mapped_column(Integer)

    invoice: Mapped["Invoices"] = relationship(
        "Invoices", back_populates="transaction_records"
    )
    item: Mapped["Items"] = relationship("Items", back_populates="transaction_records")
    discount_record_deletions: Mapped[list["DiscountRecordDeletions"]] = relationship(
        "DiscountRecordDeletions",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="transaction_record",
    )
    discount_records: Mapped[list["DiscountRecords"]] = relationship(
        "DiscountRecords",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="transaction_record",
    )
    transaction_record_edits: Mapped[list["TransactionRecordEdits"]] = relationship(
        "TransactionRecordEdits",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="transaction_record",
    )


class DiscountRecordDeletions(Base):
    __tablename__ = "discount_record_deletions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_record_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_records.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )

    transaction_record: Mapped["TransactionRecords"] = relationship(
        "TransactionRecords", back_populates="discount_record_deletions"
    )


class DiscountRecords(Base):
    __tablename__ = "discount_records"
    __table_args__ = (UniqueConstraint("transaction_record_id", "step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_record_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_records.id", ondelete="CASCADE"),
        nullable=False,
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
    discount_record_edits: Mapped[list["DiscountRecordEdits"]] = relationship(
        "DiscountRecordEdits",
        cascade="all, delete-orphan",
        passive_deletes=True,
        back_populates="discount_record",
    )


class TransactionRecordEdits(Base):
    __tablename__ = "transaction_record_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_record_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_records.id", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    previous_value: Mapped[str] = mapped_column(Text, nullable=False)
    current_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )

    transaction_record: Mapped["TransactionRecords"] = relationship(
        "TransactionRecords", back_populates="transaction_record_edits"
    )


class DiscountRecordEdits(Base):
    __tablename__ = "discount_record_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discount_record_id: Mapped[int] = mapped_column(
        ForeignKey("discount_records.id", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    previous_value: Mapped[str] = mapped_column(Text, nullable=False)
    current_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("unixepoch()")
    )

    discount_record: Mapped["DiscountRecords"] = relationship(
        "DiscountRecords", back_populates="discount_record_edits"
    )
