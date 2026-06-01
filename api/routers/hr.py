"""HR router — Document_ПриемНаРаботу."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from api.odata_client import ODataClient, ODataError
from api.schemas import HireEmployee, HireEmployeeResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/hr", tags=["hr"])

ENTITY_HIRE = "Document_ПриемНаРаботу"


def _get_client(request: Request) -> ODataClient:
    return request.app.state.odata_client


@router.post("/hire", response_model=HireEmployeeResponse, status_code=201)
async def hire_employee(
    body: HireEmployee,
    client: ODataClient = Depends(_get_client),
) -> HireEmployeeResponse:
    """Оформити прийом нового співробітника на роботу."""
    payload: dict[str, Any] = {
        "Date": body.date.isoformat(),
        "ФИО": body.employee_name,
        **body.extra,
    }
    if body.birth_date:
        payload["ДатаРождения"] = body.birth_date.isoformat()
    if body.position:
        payload["Должность"] = body.position
    if body.salary is not None:
        payload["Оклад"] = body.salary

    log.info("hire_employee", name=body.employee_name, date=body.date)
    try:
        raw = await client.post(ENTITY_HIRE, body=payload)
    except ODataError as exc:
        status = 400 if exc.status_code in (400, 422) else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    d = raw.get("d", raw)
    return HireEmployeeResponse(
        ref=d.get("Ref_Key", ""),
        number=d.get("Number"),
        date=d.get("Date", body.date),
    )
