import dotenv from 'dotenv';
dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || '5000', 10),
  nodeEnv: process.env.NODE_ENV || 'development',
  jwtSecret: process.env.JWT_SECRET || 'clinic-erp-secret-key-default-2026',
  corsOrigin: process.env.CORS_ORIGIN || 'http://localhost:3000',
  clinicName: process.env.CLINIC_NAME || 'Apex Health PolyClinic & Diagnostic Center',
};
