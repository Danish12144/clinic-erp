from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.doctors.router import router as doctors_router
from app.modules.patients.router import router as patients_router
from app.modules.tenancy.router import branch_router, clinic_router

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


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
