# Clinic ERP (Enterprise Resource Planning)

A modern, full-stack, enterprise-grade Clinic Management & ERP System engineered for outpatient clinics, polyclinics, specialized medical practices, and diagnostic centers.

---

## 🏥 Key Features

- **Electronic Health Records (EHR / EMR)**: Comprehensive patient profiles, medical history, vitals tracking, allergies, past diagnoses, and encounters.
- **Appointment Scheduling**: Real-time doctor availability calendars, automated slot management, multi-doctor queue tracking, and walk-in support.
- **Clinical Prescriptions & EHR Integration**: Digital prescription generation linked directly with patient records and the pharmacy inventory.
- **Pharmacy & Stock Inventory**: Real-time batch and expiry monitoring, inventory alerts, SKU tracking, and direct point-of-dispensing.
- **Laboratory & Diagnostics**: Test order management, specimen collection status, lab result reporting, and attachment to patient charts.
- **Billing, Invoicing & Cashier POS**: Itemized consultation & procedure charges, pharmacy checkout, lab test billing, discount & tax management, and receipt printing.
- **Role-Based Access Control (RBAC)**: Fine-grained permissions for Super Admin, Doctors, Nurses, Receptionists, Pharmacists, Lab Techs, and Patients.
- **Executive Analytics & Reporting**: Real-time operational dashboards for clinic revenue, patient footfall, doctor workload, and stock metrics.

---

## 📁 Repository Structure

```text
clinic-erp/
│
├── docs/                      # Architecture, database schema, API documentation
│   ├── architecture.md
│   ├── database-schema.md
│   └── api-spec.md
│
├── frontend/                  # React + TypeScript + Vite SPA dashboard
│   ├── src/
│   │   ├── components/        # UI widgets, layout, forms, charts
│   │   ├── pages/             # EHR, Appointments, Pharmacy, Lab, Billing, etc.
│   │   ├── services/          # API layer and data providers
│   │   ├── types/             # Frontend TypeScript models
│   │   └── styles/            # Theme & design system tokens
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                   # Node.js + Express + TypeScript API server
│   ├── src/
│   │   ├── modules/           # Auth, Patients, Appointments, Billing, Pharmacy, Lab, Analytics
│   │   ├── middleware/        # Auth, RBAC, error handlers, logging
│   │   ├── config/            # Env and database connection
│   │   ├── types/             # Domain models & DTOs
│   │   ├── app.ts             # Express app setup
│   │   └── server.ts          # Server entrypoint
│   ├── package.json
│   └── tsconfig.json
│
├── infrastructure/            # Multi-service Docker configurations & environment
│   ├── docker/
│   │   ├── Dockerfile.frontend
│   │   └── Dockerfile.backend
│   ├── docker-compose.yml
│   └── .env.example
│
├── tests/                     # Automated test suites (Unit, Integration, E2E)
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── .gitignore
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher)
- [npm](https://www.npmjs.com/) (v9 or higher)
- [Docker](https://www.docker.com/) (Optional, for containerized deployment)

### 1. Clone & Setup Environment
```bash
git clone <repository-url>
cd clinic-erp
```

Copy the environment configuration template:
```bash
cp infrastructure/.env.example .env
```

### 2. Run Backend
```bash
cd backend
npm install
npm run dev
```
The backend API server will start at `http://localhost:5000`.

### 3. Run Frontend
In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
The frontend application will start at `http://localhost:3000`.

### 4. Running with Docker Compose
To spin up all services (Frontend, Backend, PostgreSQL, and Redis) simultaneously:
```bash
docker compose -f infrastructure/docker-compose.yml up --build
```

---

## 🔐 Default Demo Accounts

| Role | Username / Email | Password | Scope / Permissions |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin@clinic.com` | `admin123` | Full access, settings, RBAC, reports |
| **Doctor** | `dr.smith@clinic.com` | `doctor123` | Patients, EHR, Consultations, Prescriptions |
| **Receptionist** | `reception@clinic.com` | `reception123` | Patient Registration, Appointments, Queue |
| **Pharmacist** | `pharma@clinic.com` | `pharma123` | Pharmacy POS, Inventory, Dispensing |
| **Lab Technician** | `lab@clinic.com` | `lab123` | Lab Orders, Specimen, Test Reports |

---

## 📖 Documentation
Detailed technical specifications and architectural documentation can be found in the [`docs/`](file:///c:/Users/DANISH%20IBRAHIM/Desktop/Project/clinic-erp/docs/) directory:
- [Architecture & System Design](file:///c:/Users/DANISH%20IBRAHIM/Desktop/Project/clinic-erp/docs/architecture.md)
- [Database Schema & ERD](file:///c:/Users/DANISH%20IBRAHIM/Desktop/Project/clinic-erp/docs/database-schema.md)
- [REST API Specifications](file:///c:/Users/DANISH%20IBRAHIM/Desktop/Project/clinic-erp/docs/api-spec.md)

---

## 🧪 Testing
Run the test suites:
```bash
# Backend unit & integration tests
cd backend && npm test

# Frontend unit & component tests
cd frontend && npm test

# Integration & E2E tests
cd tests && npm run test:e2e
```

---

## 📄 License
This project is licensed under the MIT License.
