import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import { config } from './config/index.js';
import { mockPatients, mockAppointments, mockMedicines, mockLabOrders, mockInvoices, mockUsers } from './data/mockData.js';

export function createApp(): Express {
  const app = express();

  app.use(cors({ origin: config.corsOrigin, credentials: true }));
  app.use(express.json());

  // Health check
  app.get('/health', (req: Request, res: Response) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString(), clinic: config.clinicName });
  });

  // Auth routes
  app.post('/api/v1/auth/login', (req: Request, res: Response) => {
    const { email } = req.body;
    const user = mockUsers.find(u => u.email === email) || mockUsers[0];
    res.json({ token: 'mock-jwt-token-2026', user });
  });

  app.get('/api/v1/auth/me', (req: Request, res: Response) => {
    res.json({ user: mockUsers[0] });
  });

  // Patients routes
  app.get('/api/v1/patients', (req: Request, res: Response) => {
    res.json({ patients: mockPatients, count: mockPatients.length });
  });

  app.get('/api/v1/patients/:id', (req: Request, res: Response) => {
    const patient = mockPatients.find(p => p.id === req.params.id);
    if (!patient) return res.status(404).json({ error: 'Patient not found' });
    res.json({ patient });
  });

  // Appointments routes
  app.get('/api/v1/appointments', (req: Request, res: Response) => {
    res.json({ appointments: mockAppointments });
  });

  // Pharmacy routes
  app.get('/api/v1/pharmacy/medicines', (req: Request, res: Response) => {
    res.json({ medicines: mockMedicines });
  });

  // Lab routes
  app.get('/api/v1/lab/orders', (req: Request, res: Response) => {
    res.json({ labOrders: mockLabOrders });
  });

  // Invoices routes
  app.get('/api/v1/invoices', (req: Request, res: Response) => {
    res.json({ invoices: mockInvoices });
  });

  // Error handling middleware
  app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
    console.error('Server error:', err);
    res.status(500).json({ error: 'Internal Server Error', message: err.message });
  });

  return app;
}
