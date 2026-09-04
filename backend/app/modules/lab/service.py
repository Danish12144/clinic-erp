"""Pathology / Diagnostic Lab Management business logic — see
app/modules/lab/models.py's module docstring and PRD-ARCHITECTURE.md
§5.5/§19.

Status machine (by direct instruction — see migration 0018's docstring
for the `RESULTED` deviation from the PRD's own narrative):
`ORDERED -> SAMPLE_COLLECTED -> RESULTED -> COMPLETED`, with `CANCELLED`
reachable from any state except `COMPLETED`. Only `complete_order`
finalizes results (locks them — no update/delete endpoint exists for a
`LabResult` at all, matching the "report is finalized... locked from
edits" PRD narrative at the app-convention level, not a DB trigger).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.checkin.repository import EncounterRepository
from app.modules.doctors.repository import DoctorRepository
from app.modules.lab.models import LabOrder, LabOrderStatus, LabResultFlag
from app.modules.lab.repository import LabOrderRepository, LabResultRepository, LabTestRepository
from app.modules.lab.schemas import (
    LabOrderCancelRequest,
    LabOrderCreateRequest,
    LabOrderListResponse,
    LabOrderSummary,
    LabResultCreateRequest,
    LabResultSummary,
    LabTestCreateRequest,
    LabTestListResponse,
    LabTestSummary,
    LabTestUpdateRequest,
    ReferenceRangeEntry,
)
from app.modules.patients.repository import PatientRepository

_NON_TERMINAL_STATUSES = (LabOrderStatus.ORDERED, LabOrderStatus.SAMPLE_COLLECTED, LabOrderStatus.RESULTED)


def _to_order_summary(order: LabOrder) -> LabOrderSummary:
    return LabOrderSummary(
        id=order.id, tenant_id=order.tenant_id, encounter_id=order.encounter_id, patient_id=order.patient_id,
        doctor_id=order.doctor_id, test=LabTestSummary.model_validate(order.test), ordered_by=order.ordered_by,
        status=order.status.value, ordered_at=order.ordered_at, sample_collected_at=order.sample_collected_at,
        resulted_at=order.resulted_at, completed_at=order.completed_at, cancelled_at=order.cancelled_at,
        cancelled_reason=order.cancelled_reason, created_at=order.created_at, updated_at=order.updated_at,
        results=[LabResultSummary.model_validate(r) for r in order.results],
    )


def _patient_age_years(date_of_birth) -> float | None:
    if date_of_birth is None:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - date_of_birth).days / 365.25


def _select_matching_range(ranges: list[ReferenceRangeEntry], *, sex: str | None, age_years: float | None) -> ReferenceRangeEntry | None:
    """First entry whose `sex`/`age_min`/`age_max` (if set) all match the
    patient; a range with none of those constraints matches everyone."""
    for entry in ranges:
        if entry.sex is not None and entry.sex != sex:
            continue
        if entry.age_min is not None and (age_years is None or age_years < entry.age_min):
            continue
        if entry.age_max is not None and (age_years is None or age_years > entry.age_max):
            continue
        return entry
    return None


def _compute_flag(value: str, ranges: list[ReferenceRangeEntry], *, sex: str | None, age_years: float | None) -> tuple[LabResultFlag, ReferenceRangeEntry | None]:
    """Auto-flags NORMAL/LOW/HIGH from min/max reference ranges (task 3).
    Never auto-produces CRITICAL — that needs a third pair of thresholds
    this schema doesn't model (only min/max was asked for); a caller can
    still set it manually via `LabResultEntry.flag_override`. Non-numeric
    values (qualitative results like "Positive"/"Negative") are never
    auto-flagged either — there's no reference range to compare against."""
    try:
        numeric_value = float(Decimal(value))
    except (InvalidOperation, ValueError):
        return LabResultFlag.NORMAL, None

    matched = _select_matching_range(ranges, sex=sex, age_years=age_years)
    if matched is None:
        return LabResultFlag.NORMAL, None
    if matched.min is not None and numeric_value < matched.min:
        return LabResultFlag.LOW, matched
    if matched.max is not None and numeric_value > matched.max:
        return LabResultFlag.HIGH, matched
    return LabResultFlag.NORMAL, matched


def _format_reference_range(entry: ReferenceRangeEntry | None) -> str | None:
    if entry is None or (entry.min is None and entry.max is None):
        return None
    low = "" if entry.min is None else str(entry.min)
    high = "" if entry.max is None else str(entry.max)
    text = f"{low}-{high}"
    return f"{text} {entry.unit}" if entry.unit else text


class LabTestService:
    async def create_test(self, *, tenant_id: uuid.UUID, payload: LabTestCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LabTestSummary:
        async with tenant_session(tenant_id) as session:
            fields = payload.model_dump()
            fields["reference_ranges"] = [r.model_dump() for r in payload.reference_ranges]
            test = await LabTestRepository(session).create(tenant_id=tenant_id, **fields)
            summary = LabTestSummary.model_validate(test)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_test.create", entity_type="lab_test", entity_id=test.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_test(self, *, tenant_id: uuid.UUID, test_id: uuid.UUID, payload: LabTestUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LabTestSummary:
        async with tenant_session(tenant_id) as session:
            repo = LabTestRepository(session)
            test = await repo.get_by_id(test_id)
            if test is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab test not found")
            before = LabTestSummary.model_validate(test).model_dump(mode="json")

            changes = payload.model_dump(exclude_unset=True, exclude={"reference_ranges"})
            if "reference_ranges" in payload.model_fields_set:
                changes["reference_ranges"] = [r.model_dump() for r in payload.reference_ranges]
            await repo.update_fields(test_id, **changes)

            updated = await repo.get_by_id(test_id)
            after = LabTestSummary.model_validate(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_test.update", entity_type="lab_test", entity_id=test_id, before=before, after=after.model_dump(mode="json"),
            )
            return after

    async def get_test(self, *, tenant_id: uuid.UUID, test_id: uuid.UUID) -> LabTestSummary:
        async with tenant_session(tenant_id) as session:
            test = await LabTestRepository(session).get_by_id(test_id)
            if test is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab test not found")
            return LabTestSummary.model_validate(test)

    async def search_tests(self, *, tenant_id: uuid.UUID, query_text: str | None, is_active: bool | None, limit: int, offset: int) -> LabTestListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await LabTestRepository(session).search(tenant_id=tenant_id, query_text=query_text, is_active=is_active, limit=limit, offset=offset)
            return LabTestListResponse(items=[LabTestSummary.model_validate(t) for t in rows], total=total, limit=limit, offset=offset)


class LabOrderService:
    async def create_order(self, *, tenant_id: uuid.UUID, payload: LabOrderCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(payload.encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")

            test_repo = LabTestRepository(session)
            test = await test_repo.get_by_id(payload.test_id)
            if test is None or not test.is_active:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Lab test '{payload.test_id}' does not exist or is inactive")

            doctor_id = payload.doctor_id or (actor_user_id if actor_role == "DOCTOR" else None)
            if doctor_id is not None and await DoctorRepository(session).get_user_and_profile(doctor_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{doctor_id}' does not exist")

            order_repo = LabOrderRepository(session)
            order = await order_repo.create(
                tenant_id=tenant_id, encounter_id=encounter.id, patient_id=encounter.patient_id, doctor_id=doctor_id,
                test_id=test.id, ordered_by=actor_user_id,
            )
            full = await order_repo.get_by_id(order.id)
            assert full is not None
            summary = _to_order_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_order.create", entity_type="lab_order", entity_id=order.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def collect_sample(self, *, tenant_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            repo = LabOrderRepository(session)
            order = await repo.get_by_id(order_id)
            if order is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            if order.status != LabOrderStatus.ORDERED:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot collect a sample for an order with status {order.status.value}")

            before_status = order.status
            await repo.update_fields(order.id, status=LabOrderStatus.SAMPLE_COLLECTED, sample_collected_at=datetime.now(timezone.utc))
            updated = await repo.get_by_id(order.id)
            assert updated is not None
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_order.status_change", entity_type="lab_order", entity_id=order.id,
                before={"status": before_status.value}, after={"status": LabOrderStatus.SAMPLE_COLLECTED.value},
            )
            return _to_order_summary(updated)

    async def add_results(self, *, tenant_id: uuid.UUID, order_id: uuid.UUID, payload: LabResultCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            order_repo = LabOrderRepository(session)
            order = await order_repo.get_by_id(order_id)
            if order is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            if order.status not in (LabOrderStatus.SAMPLE_COLLECTED, LabOrderStatus.RESULTED):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot record results for an order with status {order.status.value}")

            patient = await PatientRepository(session).get_by_id(order.patient_id)
            age_years = _patient_age_years(patient.date_of_birth) if patient else None
            sex = patient.gender if patient else None
            reference_ranges = [ReferenceRangeEntry.model_validate(r) for r in order.test.reference_ranges]

            result_repo = LabResultRepository(session)
            for entry in payload.results:
                if entry.flag_override:
                    flag = LabResultFlag(entry.flag_override)
                    matched = _select_matching_range(reference_ranges, sex=sex, age_years=age_years)
                else:
                    flag, matched = _compute_flag(entry.value, reference_ranges, sex=sex, age_years=age_years)
                await result_repo.create(
                    tenant_id=tenant_id, lab_order_id=order.id, parameter=entry.parameter, value=entry.value,
                    unit=entry.unit or (matched.unit if matched else None), reference_range=_format_reference_range(matched),
                    flag=flag, entered_by=actor_user_id,
                )

            before_status = order.status
            new_status_fields: dict[str, object] = {}
            if order.status == LabOrderStatus.SAMPLE_COLLECTED:
                new_status_fields = {"status": LabOrderStatus.RESULTED, "resulted_at": datetime.now(timezone.utc)}
                await order_repo.update_fields(order.id, **new_status_fields)

            updated = await order_repo.get_by_id(order.id)
            assert updated is not None
            summary = _to_order_summary(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_result.record", entity_type="lab_order", entity_id=order.id, before=None,
                after={"results_added": len(payload.results)},
            )
            if new_status_fields:
                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="lab_order.status_change", entity_type="lab_order", entity_id=order.id,
                    before={"status": before_status.value}, after={"status": LabOrderStatus.RESULTED.value},
                )
            return summary

    async def complete_order(self, *, tenant_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            repo = LabOrderRepository(session)
            order = await repo.get_by_id(order_id)
            if order is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            if order.status != LabOrderStatus.RESULTED:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot complete an order with status {order.status.value}")

            await LabResultRepository(session).finalize_all_for_order(order.id)
            await repo.update_fields(order.id, status=LabOrderStatus.COMPLETED, completed_at=datetime.now(timezone.utc))
            updated = await repo.get_by_id(order.id)
            assert updated is not None
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_order.status_change", entity_type="lab_order", entity_id=order.id,
                before={"status": LabOrderStatus.RESULTED.value}, after={"status": LabOrderStatus.COMPLETED.value},
            )
            return _to_order_summary(updated)

    async def cancel_order(self, *, tenant_id: uuid.UUID, order_id: uuid.UUID, payload: LabOrderCancelRequest, actor_user_id: uuid.UUID, actor_role: str) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            repo = LabOrderRepository(session)
            order = await repo.get_by_id(order_id)
            if order is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            if order.status not in _NON_TERMINAL_STATUSES:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel an order with status {order.status.value}")

            before_status = order.status
            await repo.update_fields(order.id, status=LabOrderStatus.CANCELLED, cancelled_at=datetime.now(timezone.utc), cancelled_reason=payload.reason)
            updated = await repo.get_by_id(order.id)
            assert updated is not None
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lab_order.cancel", entity_type="lab_order", entity_id=order.id,
                before={"status": before_status.value}, after={"status": LabOrderStatus.CANCELLED.value, "reason": payload.reason},
            )
            return _to_order_summary(updated)

    async def search_orders(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, encounter_id: uuid.UUID | None, status_filter: LabOrderStatus | None,
        actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int,
    ) -> LabOrderListResponse:
        only_completed = False
        effective_patient_id = patient_id
        async with tenant_session(tenant_id) as session:
            if actor_role == "PATIENT":
                only_completed = True
                own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
                if own_patient is None:
                    return LabOrderListResponse(items=[], total=0, limit=limit, offset=offset)
                effective_patient_id = own_patient.id

            rows, total = await LabOrderRepository(session).search(
                tenant_id=tenant_id, patient_id=effective_patient_id, encounter_id=encounter_id, status=status_filter,
                only_completed=only_completed, limit=limit, offset=offset,
            )
            return LabOrderListResponse(items=[_to_order_summary(o) for o in rows], total=total, limit=limit, offset=offset)

    async def get_order(self, *, tenant_id: uuid.UUID, order_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> LabOrderSummary:
        async with tenant_session(tenant_id) as session:
            order = await LabOrderRepository(session).get_by_id(order_id)
            if order is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            if actor_role == "PATIENT":
                own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
                if own_patient is None or order.patient_id != own_patient.id or order.status != LabOrderStatus.COMPLETED:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
            return _to_order_summary(order)
