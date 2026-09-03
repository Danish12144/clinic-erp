from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.appointments.router import router as appointments_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import invoice_router as billing_invoice_router, payment_router as billing_payment_router
from app.modules.checkin.router import encounter_router, queue_router
from app.modules.consultation.router import consultation_router, prescription_router
from app.modules.doctors.router import router as doctors_router
from app.modules.letterhead.router import router as letterhead_router
from app.modules.patients.router import router as patients_router
from app.modules.reports.router import billing_summary_router, financial_report_router
from app.modules.staff.router import router as staff_router
from app.modules.tenancy.router import branch_router, clinic_router
from app.modules.vitals.router import router as vitals_router

settings = get_settings()

app = FastAPI(title="Clinic ERP + CRM API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(clinic_router)
app.include_router(branch_router)
app.include_router(patients_router)
app.include_router(doctors_router)
app.include_router(staff_router)
app.include_router(audit_router)
app.include_router(appointments_router)
app.include_router(encounter_router)
app.include_router(queue_router)
app.include_router(vitals_router)
app.include_router(consultation_router)
app.include_router(prescription_router)
app.include_router(letterhead_router)
app.include_router(billing_invoice_router)
app.include_router(billing_payment_router)
app.include_router(billing_summary_router)
app.include_router(financial_report_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
