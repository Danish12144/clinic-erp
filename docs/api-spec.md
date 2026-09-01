# Clinic ERP REST API Specifications

Base URL: `http://localhost:5000/api/v1`

## 1. Authentication & Users
- `POST /auth/login` - Authenticate user & issue JWT token
- `POST /auth/register` - Create user profile (Admin only)
- `GET  /auth/me` - Get current authenticated user profile
- `GET  /users/doctors` - Get list of active clinic doctors & rosters

## 2. Patients & EHR
- `GET    /patients` - Query patient directory with search, filter, pagination
- `POST   /patients` - Register a new patient
- `GET    /patients/:id` - Retrieve comprehensive patient profile
- `PUT    /patients/:id` - Update patient demographics & emergency contacts
- `GET    /patients/:id/medical-records` - Retrieve patient EHR encounters & vitals
- `POST   /patients/:id/medical-records` - Record consultation, diagnoses, and vitals

## 3. Appointments & Queue
- `GET    /appointments` - Query appointments by date, doctor, or status
- `POST   /appointments` - Schedule a new appointment slot
- `PUT    /appointments/:id/status` - Update appointment progress (`CHECKED_IN`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`)
- `GET    /appointments/today-queue` - Live clinic queue for triage/reception

## 4. Billing & Cashier POS
- `GET    /invoices` - List invoices with payment statuses
- `POST   /invoices` - Generate itemized invoice (consultation, pharmacy, lab)
- `GET    /invoices/:id` - Fetch invoice details & printable receipt payload
- `POST   /invoices/:id/payments` - Record payment transaction (Cash, Card, UPI, Insurance)

## 5. Pharmacy & Inventory
- `GET    /pharmacy/medicines` - List drug inventory, stock levels, and alert flags
- `POST   /pharmacy/medicines` - Register new medicine SKU
- `PUT    /pharmacy/medicines/:id/stock` - Adjust / replenish stock batch
- `GET    /pharmacy/prescriptions/pending` - Prescriptions awaiting dispensing
- `POST   /pharmacy/prescriptions/:id/dispense` - Dispense medication & deduct stock

## 6. Laboratory & Diagnostics
- `GET    /lab/orders` - List lab test orders
- `POST   /lab/orders` - Place diagnostic test order for patient
- `PUT    /lab/orders/:id/results` - Submit specimen results & range flags
- `GET    /lab/orders/:id/report` - Generate diagnostic test report

## 7. Analytics & Reports
- `GET    /analytics/overview` - Clinic KPI overview (daily footfall, revenue, doctor workload, low stock count)
- `GET    /analytics/revenue-trends` - Financial breakdown by department and period
