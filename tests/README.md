# Clinic ERP - Test Suite

This directory contains test suites for unit testing, backend integration testing, and full end-to-end clinical workflow automation.

## Directory Layout
- `unit/`: Unit tests for domain logic (e.g. prescription validation, billing calculations, dosage limits).
- `integration/`: API contract and endpoint integration tests (e.g. Auth, Patient EHR endpoints, Inventory deduction).
- `e2e/`: Full end-to-end patient encounter workflow tests (Registration -> Doctor Consultation -> Prescription -> Pharmacy POS -> Invoicing).

## Running Tests
```bash
# Run all tests
npm test

# Run unit tests only
npm run test:unit

# Run integration tests
npm run test:integration

# Run E2E tests
npm run test:e2e
```
