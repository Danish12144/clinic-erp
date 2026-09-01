export type UserRole = 
  | 'SUPER_ADMIN' 
  | 'DOCTOR' 
  | 'RECEPTIONIST' 
  | 'PHARMACIST' 
  | 'LAB_TECH' 
  | 'PATIENT';

export interface User {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  phone?: string;
  specialization?: string;
  isActive: boolean;
  avatarUrl?: string;
}

export interface Patient {
  id: string;
  mrn: string;
  firstName: string;
  lastName: string;
  gender: 'Male' | 'Female' | 'Other';
  dateOfBirth: string;
  phone: string;
  email: string;
  bloodGroup: string;
  allergies: string[];
  chronicConditions: string[];
  emergencyContact: {
    name: string;
    phone: string;
    relationship: string;
  };
  address: string;
  createdAt: string;
}

export interface Appointment {
  id: string;
  patientId: string;
  patientName: string;
  doctorId: string;
  doctorName: string;
  department: string;
  scheduledTime: string;
  durationMinutes: number;
  status: 'SCHEDULED' | 'CHECKED_IN' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
  type: 'General Checkup' | 'Follow-up' | 'Emergency' | 'Specialist Consultation';
  tokenNumber: number;
  notes?: string;
}

export interface MedicalRecord {
  id: string;
  patientId: string;
  doctorId: string;
  doctorName: string;
  appointmentId?: string;
  date: string;
  vitals: {
    bloodPressure: string;
    heartRate: number;
    temperature: number;
    oxygenSaturation: number;
    weightKg: number;
    heightCm: number;
    bmi: number;
  };
  chiefComplaint: string;
  diagnosis: string;
  icdCode?: string;
  clinicalNotes: string;
  prescriptions: PrescriptionItem[];
}

export interface PrescriptionItem {
  id: string;
  medicineId: string;
  medicineName: string;
  dosage: string;
  frequency: string;
  duration: string;
  quantity: number;
  instructions: string;
}

export interface Medicine {
  id: string;
  sku: string;
  name: string;
  genericName: string;
  category: 'Antibiotic' | 'Analgesic' | 'Antihistamine' | 'Cardiovascular' | 'Vitamins' | 'Gastrointestinal';
  stockCount: number;
  minThreshold: number;
  unitPrice: number;
  dosageForm: 'Tablet' | 'Capsule' | 'Syrup' | 'Injection' | 'Ointment';
  batchNumber: string;
  expiryDate: string;
}

export interface LabOrder {
  id: string;
  orderNumber: string;
  patientId: string;
  patientName: string;
  doctorId: string;
  doctorName: string;
  testName: string;
  category: 'Hematology' | 'Biochemistry' | 'Radiology' | 'Microbiology' | 'Pathology';
  status: 'ORDERED' | 'SAMPLE_COLLECTED' | 'PROCESSING' | 'COMPLETED';
  price: number;
  orderedAt: string;
  results?: LabResultItem[];
}

export interface LabResultItem {
  parameter: string;
  value: string;
  unit: string;
  referenceRange: string;
  flag: 'NORMAL' | 'LOW' | 'HIGH' | 'CRITICAL';
}

export interface Invoice {
  id: string;
  invoiceNumber: string;
  patientId: string;
  patientName: string;
  items: {
    description: string;
    category: 'Consultation' | 'Pharmacy' | 'Lab Test' | 'Procedure';
    quantity: number;
    unitPrice: number;
    total: number;
  }[];
  subtotal: number;
  tax: number;
  discount: number;
  total: number;
  status: 'PAID' | 'UNPAID' | 'PARTIALLY_PAID';
  paymentMethod?: 'CASH' | 'CARD' | 'UPI' | 'INSURANCE';
  createdAt: string;
}
