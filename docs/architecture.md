# Clinic ERP System Architecture

## 1. System Overview

Clinic ERP is structured around a decoupled, micro-modular client-server architecture designed for high availability, HIPAA compliance readiness, auditability, and clinical workflow efficiency.

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Presentation Layer (Frontend)"]
        A1["Doctor Dashboard (EHR, Prescriptions)"]
        A2["Receptionist Portal (Queue, Appointments)"]
        A3["Pharmacy POS & Inventory"]
        A4["Laboratory Test Desk"]
        A5["Billing & Cashier Terminal"]
        A6["Super Admin Analytics & Config"]
    end

    subgraph Gateway ["API Gateway & Security"]
        GW["Reverse Proxy / Nginx / Express API Gateway"]
        AuthMiddleware["JWT Authentication & RBAC Guard"]
        RateLimit["Rate Limiter & Request Sanitizer"]
    end

    subgraph BackendServices ["Backend Core Services (REST API)"]
        S1["Auth & User Management"]
        S2["Patient & EHR Service"]
        S3["Appointment & Scheduling Engine"]
        S4["Billing & Invoicing Service"]
        S5["Pharmacy & Inventory Service"]
        S6["Lab & Diagnostic Service"]
        S7["Analytics & Audit Logging Engine"]
    end

    subgraph DataStorage ["Data & Cache Layer"]
        DB[("PostgreSQL / SQLite Database")]
        Redis[("Redis Session & Cache")]
        Storage[("Encrypted Medical Document Storage")]
    end

    ClientLayer --> GW
    GW --> AuthMiddleware --> RateLimit --> BackendServices
    BackendServices --> DB
    BackendServices --> Redis
    BackendServices --> Storage
```

---

## 2. Core Architectural Pillars

### A. Role-Based Access Control (RBAC)
Security is enforced both at the gateway and the service layer. Every request contains an authenticated JWT with role scopes:
- **`SUPER_ADMIN`**: Full administrative privileges, audit logs, doctor roster configuration, user provisioning.
- **`DOCTOR`**: Access to assigned patient records, clinical notes, diagnosis codes (ICD-10), digital prescriptions, lab orders.
- **`RECEPTIONIST`**: Patient intake, scheduling, queue prioritization, walk-in registration, preliminary vitals intake.
- **`PHARMACIST`**: Prescription fulfillment, medicine stock catalog, batch/expiry alerts, direct sales, restocking.
- **`LAB_TECH`**: Specimen accessioning, test entry, diagnostic results upload, status transition (Pending -> Processing -> Completed).
- **`ACCOUNTANT / CASHIER`**: Invoices, payment receipts, refunds, tax summaries, insurance co-pay tracking.
- **`PATIENT`**: Self-service portal (viewing past encounters, lab reports, booking appointments).

### B. High Reliability & Data Integrity
- Atomic transactions for multi-step operations (e.g., dispensing medicine updates pharmacy inventory and creates invoice items in a single transaction).
- Detailed immutable audit trail logging all EHR modifications, sensitive data access, and financial transactions.

---

## 3. Communication Protocols

- **RESTful API**: Clean JSON REST endpoints versioned under `/api/v1/*`.
- **WebSocket / Server-Sent Events (SSE)**: For real-time appointment queue status updates and low-stock alerts.
