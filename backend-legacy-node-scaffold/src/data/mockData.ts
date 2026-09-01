import { User, Patient, Appointment, MedicalRecord, Medicine, LabOrder, Invoice } from '../types/index.js';

export const mockUsers: User[] = [
  {
    id: 'usr-1',
    email: 'admin@clinic.com',
    fullName: 'Dr. Sarah Jenkins',
    role: 'SUPER_ADMIN',
    phone: '+1 (555) 019-2831',
    specialization: 'Chief Medical Officer / Internal Medicine',
    isActive: true,
    avatarUrl: 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=200'
  },
  {
    id: 'usr-2',
    email: 'dr.smith@clinic.com',
    fullName: 'Dr. Arthur Smith',
    role: 'DOCTOR',
    phone: '+1 (555) 019-4829',
    specialization: 'Cardiology',
    isActive: true,
    avatarUrl: 'https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=200'
  },
  {
    id: 'usr-3',
    email: 'dr.elena@clinic.com',
    fullName: 'Dr. Elena Rostova',
    role: 'DOCTOR',
    phone: '+1 (555) 019-8833',
    specialization: 'Pediatrics',
    isActive: true,
    avatarUrl: 'https://images.unsplash.com/photo-1594824813626-d98f7e25287f?auto=format&fit=crop&q=80&w=200'
  },
  {
    id: 'usr-4',
    email: 'reception@clinic.com',
    fullName: 'Mark Davis',
    role: 'RECEPTIONIST',
    phone: '+1 (555) 019-5512',
    isActive: true,
  },
  {
    id: 'usr-5',
    email: 'pharma@clinic.com',
    fullName: 'Linda Vance (R.Ph)',
    role: 'PHARMACIST',
    phone: '+1 (555) 019-7744',
    isActive: true,
  },
  {
    id: 'usr-6',
    email: 'lab@clinic.com',
    fullName: 'David Kalu',
    role: 'LAB_TECH',
    phone: '+1 (555) 019-9921',
    isActive: true,
  }
];

export const mockPatients: Patient[] = [
  {
    id: 'pat-1',
    mrn: 'MRN-2026-0089',
    firstName: 'Eleanor',
    lastName: 'Vance',
    gender: 'Female',
    dateOfBirth: '1988-04-12',
    phone: '+1 (555) 234-5678',
    email: 'eleanor.vance@example.com',
    bloodGroup: 'O+',
    allergies: ['Penicillin', 'Peanuts'],
    chronicConditions: ['Hypertension', 'Mild Asthma'],
    emergencyContact: {
      name: 'Thomas Vance',
      phone: '+1 (555) 234-5679',
      relationship: 'Spouse'
    },
    address: '742 Evergreen Terrace, Springfield',
    createdAt: '2026-01-15T08:30:00Z'
  },
  {
    id: 'pat-2',
    mrn: 'MRN-2026-0142',
    firstName: 'Marcus',
    lastName: 'Holloway',
    gender: 'Male',
    dateOfBirth: '1995-11-03',
    phone: '+1 (555) 345-6789',
    email: 'marcus.h@example.com',
    bloodGroup: 'A+',
    allergies: ['Sulfa Drugs'],
    chronicConditions: [],
    emergencyContact: {
      name: 'Angela Holloway',
      phone: '+1 (555) 345-0000',
      relationship: 'Mother'
    },
    address: '1088 Mission St, San Francisco',
    createdAt: '2026-02-10T10:15:00Z'
  },
  {
    id: 'pat-3',
    mrn: 'MRN-2026-0198',
    firstName: 'Clara',
    lastName: 'Oswald',
    gender: 'Female',
    dateOfBirth: '1992-06-24',
    phone: '+1 (555) 456-7890',
    email: 'clara.oswald@example.com',
    bloodGroup: 'B-',
    allergies: [],
    chronicConditions: ['Type 1 Diabetes'],
    emergencyContact: {
      name: 'Danny Pink',
      phone: '+1 (555) 456-1122',
      relationship: 'Partner'
    },
    address: '42 Baker Street, London Way',
    createdAt: '2026-02-28T14:45:00Z'
  }
];

export const mockAppointments: Appointment[] = [
  {
    id: 'apt-1',
    patientId: 'pat-1',
    patientName: 'Eleanor Vance',
    doctorId: 'usr-2',
    doctorName: 'Dr. Arthur Smith',
    department: 'Cardiology',
    scheduledTime: '2026-09-02T09:30:00Z',
    durationMinutes: 30,
    status: 'IN_PROGRESS',
    type: 'Specialist Consultation',
    tokenNumber: 1,
    notes: 'Routine blood pressure review and ECG follow-up.'
  },
  {
    id: 'apt-2',
    patientId: 'pat-2',
    patientName: 'Marcus Holloway',
    doctorId: 'usr-1',
    doctorName: 'Dr. Sarah Jenkins',
    department: 'Internal Medicine',
    scheduledTime: '2026-09-02T10:15:00Z',
    durationMinutes: 20,
    status: 'CHECKED_IN',
    type: 'General Checkup',
    tokenNumber: 2,
    notes: 'Complaining of recurrent migraines and fatigue.'
  },
  {
    id: 'apt-3',
    patientId: 'pat-3',
    patientName: 'Clara Oswald',
    doctorId: 'usr-3',
    doctorName: 'Dr. Elena Rostova',
    department: 'Pediatrics',
    scheduledTime: '2026-09-02T11:00:00Z',
    durationMinutes: 30,
    status: 'SCHEDULED',
    type: 'Follow-up',
    tokenNumber: 3,
    notes: 'Quarterly HbA1c progress review.'
  }
];

export const mockMedicines: Medicine[] = [
  {
    id: 'med-1',
    sku: 'MED-AMX-500',
    name: 'Amoxicillin 500mg',
    genericName: 'Amoxicillin Trihydrate',
    category: 'Antibiotic',
    stockCount: 420,
    minThreshold: 100,
    unitPrice: 14.50,
    dosageForm: 'Capsule',
    batchNumber: 'BCH-2026-08',
    expiryDate: '2027-11-30'
  },
  {
    id: 'med-2',
    sku: 'MED-ATM-050',
    name: 'Atenolol 50mg',
    genericName: 'Atenolol',
    category: 'Cardiovascular',
    stockCount: 48,
    minThreshold: 50,
    unitPrice: 22.00,
    dosageForm: 'Tablet',
    batchNumber: 'BCH-2025-14',
    expiryDate: '2027-04-15'
  },
  {
    id: 'med-3',
    sku: 'MED-PCM-650',
    name: 'Paracetamol 650mg',
    genericName: 'Acetaminophen',
    category: 'Analgesic',
    stockCount: 1250,
    minThreshold: 200,
    unitPrice: 5.00,
    dosageForm: 'Tablet',
    batchNumber: 'BCH-2026-19',
    expiryDate: '2028-01-01'
  },
  {
    id: 'med-4',
    sku: 'MED-CTZ-010',
    name: 'Cetirizine 10mg',
    genericName: 'Cetirizine Hydrochloride',
    category: 'Antihistamine',
    stockCount: 310,
    minThreshold: 80,
    unitPrice: 8.75,
    dosageForm: 'Tablet',
    batchNumber: 'BCH-2026-02',
    expiryDate: '2027-09-20'
  }
];

export const mockLabOrders: LabOrder[] = [
  {
    id: 'lab-1',
    orderNumber: 'LAB-2026-0419',
    patientId: 'pat-1',
    patientName: 'Eleanor Vance',
    doctorId: 'usr-2',
    doctorName: 'Dr. Arthur Smith',
    testName: 'Lipid Profile & Serum Electrolytes',
    category: 'Biochemistry',
    status: 'COMPLETED',
    price: 85.00,
    orderedAt: '2026-09-01T14:20:00Z',
    results: [
      { parameter: 'Total Cholesterol', value: '215', unit: 'mg/dL', referenceRange: '< 200', flag: 'HIGH' },
      { parameter: 'HDL Cholesterol', value: '55', unit: 'mg/dL', referenceRange: '> 40', flag: 'NORMAL' },
      { parameter: 'LDL Cholesterol', value: '138', unit: 'mg/dL', referenceRange: '< 100', flag: 'HIGH' },
      { parameter: 'Triglycerides', value: '160', unit: 'mg/dL', referenceRange: '< 150', flag: 'HIGH' },
      { parameter: 'Serum Potassium', value: '4.2', unit: 'mmol/L', referenceRange: '3.5 - 5.0', flag: 'NORMAL' }
    ]
  },
  {
    id: 'lab-2',
    orderNumber: 'LAB-2026-0420',
    patientId: 'pat-3',
    patientName: 'Clara Oswald',
    doctorId: 'usr-3',
    doctorName: 'Dr. Elena Rostova',
    testName: 'Glycated Hemoglobin (HbA1c)',
    category: 'Hematology',
    status: 'PROCESSING',
    price: 45.00,
    orderedAt: '2026-09-02T08:15:00Z'
  }
];

export const mockInvoices: Invoice[] = [
  {
    id: 'inv-1',
    invoiceNumber: 'INV-2026-1001',
    patientId: 'pat-1',
    patientName: 'Eleanor Vance',
    items: [
      { description: 'Cardiology Specialist Consultation', category: 'Consultation', quantity: 1, unitPrice: 120.00, total: 120.00 },
      { description: 'Lipid Profile & Serum Electrolytes', category: 'Lab Test', quantity: 1, unitPrice: 85.00, total: 85.00 },
      { description: 'Atenolol 50mg (30 Tablets)', category: 'Pharmacy', quantity: 1, unitPrice: 22.00, total: 22.00 }
    ],
    subtotal: 227.00,
    tax: 11.35,
    discount: 10.00,
    total: 228.35,
    status: 'PAID',
    paymentMethod: 'CARD',
    createdAt: '2026-09-01T15:45:00Z'
  },
  {
    id: 'inv-2',
    invoiceNumber: 'INV-2026-1002',
    patientId: 'pat-2',
    patientName: 'Marcus Holloway',
    items: [
      { description: 'Internal Medicine Consultation', category: 'Consultation', quantity: 1, unitPrice: 75.00, total: 75.00 }
    ],
    subtotal: 75.00,
    tax: 3.75,
    discount: 0.00,
    total: 78.75,
    status: 'UNPAID',
    createdAt: '2026-09-02T10:20:00Z'
  }
];
