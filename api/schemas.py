"""Pydantic schemas for FastAPI request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Generic schemas (used by metadata router)
# ---------------------------------------------------------------------------

class EntityQueryParams(BaseModel):
    """OData query parameters — used by metadata router only."""

    filter: str | None = Field(default=None)
    top: int = Field(default=50, ge=1, le=200)
    skip: int = Field(default=0, ge=0)
    orderby: str | None = Field(default=None)


class EntityListResponse(BaseModel):
    count: int
    items: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Counterparty (Catalog_Контрагенты)
# ---------------------------------------------------------------------------

class Counterparty(BaseModel):
    """Контрагент — юридична або фізична особа."""

    ref: str = Field(alias="Ref_Key", description="Унікальний ідентифікатор")
    code: str | None = Field(alias="Code", default=None, description="Код контрагента")
    name: str = Field(alias="Description", description="Назва контрагента")
    type: str | None = Field(alias="ВидКонтрагента", default=None, description="ЮридическоеЛицо / ФизическоеЛицо")
    edrpou: str | None = Field(alias="КодПоЕДРПОУ", default=None, description="ЄДРПОУ")
    inn: str | None = Field(alias="ИНН", default=None, description="ІПН фізособи")
    is_buyer: bool | None = Field(alias="Покупатель", default=None, description="Є покупцем")
    is_supplier: bool | None = Field(alias="Поставщик", default=None, description="Є постачальником")
    is_active: bool | None = Field(alias="Недействителен", default=None, description="Недійсний")
    created_at: datetime | None = Field(alias="ДатаСоздания", default=None, description="Дата створення")
    notes: str | None = Field(alias="ОсновныеСведения", default=None, description="Основні відомості")

    model_config = {"populate_by_name": True}


class CounterpartyListResponse(BaseModel):
    count: int
    items: list[Counterparty]


# ---------------------------------------------------------------------------
# Invoice from buyer (Document_СчетНаОплату)
# ---------------------------------------------------------------------------

class Invoice(BaseModel):
    """Рахунок на оплату покупцю."""

    ref: str = Field(alias="Ref_Key", description="Унікальний ідентифікатор")
    number: str | None = Field(alias="Number", default=None, description="Номер документа")
    date: datetime | None = Field(alias="Date", default=None, description="Дата документа")
    posted: bool | None = Field(alias="Posted", default=None, description="Проведено")
    amount: float | None = Field(alias="СуммаДокумента", default=None, description="Сума документа")
    includes_vat: bool | None = Field(alias="СуммаВключаетНДС", default=None, description="Сума включає ПДВ")
    payment_type: str | None = Field(alias="ТипДенежныхСредств", default=None, description="Тип грошових коштів")
    basis: str | None = Field(alias="ОснованиеПечати", default=None, description="Підстава (договір)")

    model_config = {"populate_by_name": True}


class InvoiceListResponse(BaseModel):
    count: int
    items: list[Invoice]


# ---------------------------------------------------------------------------
# Invoice from supplier (Document_СчетНаОплатуПоставщика)
# ---------------------------------------------------------------------------

class SupplierInvoice(BaseModel):
    """Рахунок на оплату від постачальника."""

    ref: str = Field(alias="Ref_Key", description="Унікальний ідентифікатор")
    number: str | None = Field(alias="Number", default=None, description="Номер документа")
    date: datetime | None = Field(alias="Date", default=None, description="Дата документа")
    posted: bool | None = Field(alias="Posted", default=None, description="Проведено")
    amount: float | None = Field(alias="СуммаДокумента", default=None, description="Сума документа")
    includes_vat: bool | None = Field(alias="СуммаВключаетНДС", default=None, description="Сума включає ПДВ")
    payment_type: str | None = Field(alias="ТипДенежныхСредств", default=None, description="Тип грошових коштів")
    basis: str | None = Field(alias="ОснованиеПечати", default=None, description="Підстава (договір)")

    model_config = {"populate_by_name": True}


class SupplierInvoiceListResponse(BaseModel):
    count: int
    items: list[SupplierInvoice]


# ---------------------------------------------------------------------------
# Act of completed work (Document_АктВыполненныхРабот)
# ---------------------------------------------------------------------------

class Act(BaseModel):
    """Акт виконаних робіт."""

    ref: str = Field(alias="Ref_Key", description="Унікальний ідентифікатор")
    number: str | None = Field(alias="Number", default=None, description="Номер документа")
    date: datetime | None = Field(alias="Date", default=None, description="Дата документа")
    posted: bool | None = Field(alias="Posted", default=None, description="Проведено")
    amount: float | None = Field(alias="СуммаДокумента", default=None, description="Сума документа")
    includes_vat: bool | None = Field(alias="СуммаВключаетНДС", default=None, description="Сума включає ПДВ")
    basis: str | None = Field(alias="ОснованиеПечати", default=None, description="Підстава (договір)")

    model_config = {"populate_by_name": True}


class ActListResponse(BaseModel):
    count: int
    items: list[Act]


class ActCreate(BaseModel):
    """Дані для створення акту виконаних робіт."""

    date: datetime = Field(description="Дата акту")
    amount: float = Field(description="Сума документа")
    basis: str | None = Field(default=None, description="Підстава (договір)")
    includes_vat: bool = Field(default=True, description="Сума включає ПДВ")
    extra: dict[str, Any] = Field(default_factory=dict, description="Додаткові поля 1С")


class ActCreateResponse(BaseModel):
    item: Act


# ---------------------------------------------------------------------------
# Hire employee (Document_ПриемНаРаботу)
# ---------------------------------------------------------------------------

class HireEmployee(BaseModel):
    """Дані для оформлення прийому на роботу."""

    date: datetime = Field(description="Дата прийому")
    employee_name: str = Field(description="ПІБ співробітника")
    birth_date: datetime | None = Field(default=None, description="Дата народження")
    position: str | None = Field(default=None, description="Посада")
    salary: float | None = Field(default=None, description="Оклад (грн)")
    extra: dict[str, Any] = Field(default_factory=dict, description="Додаткові поля 1С")


class HireEmployeeResponse(BaseModel):
    ref: str = Field(description="Ref_Key створеного документа")
    number: str | None = Field(default=None, description="Номер документа")
    date: datetime = Field(description="Дата документа")
