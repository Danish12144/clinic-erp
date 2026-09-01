import React, { useState } from 'react';
import { 
  Users, 
  Calendar, 
  FileText, 
  Activity, 
  Pill, 
  TestTube, 
  DollarSign, 
  TrendingUp, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  Plus
} from 'lucide-react';

interface Patient {
  id: string;
  mrn: string;
  name: string;
  age: number;
  gender: string;
  doctor: string;
  status: 'Checked In' | 'In Consultation' | 'Completed';
  time: string;
}

const mockQueue: Patient[] = [
  { id: '1', mrn: 'MRN-2026-0089', name: 'Eleanor Vance', age: 36, gender: 'Female', doctor: 'Dr. Arthur Smith', status: 'In Consultation', time: '09:30 AM' },
  { id: '2', mrn: 'MRN-2026-0142', name: 'Marcus Holloway', age: 29, gender: 'Male', doctor: 'Dr. Sarah Jenkins', status: 'Checked In', time: '10:15 AM' },
  { id: '3', mrn: 'MRN-2026-0198', name: 'Clara Oswald', age: 32, gender: 'Female', doctor: 'Dr. Elena Rostova', status: 'Checked In', time: '11:00 AM' },
  { id: '4', mrn: 'MRN-2026-0205', name: 'James Wilson', age: 48, gender: 'Male', doctor: 'Dr. Arthur Smith', status: 'Completed', time: '08:45 AM' },
];

export function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'patients' | 'appointments' | 'pharmacy' | 'lab' | 'billing'>('dashboard');

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">
            <Activity size={24} />
          </div>
          <div className="brand-text">
            <h1>Apex Clinic ERP</h1>
            <span>Healthcare Operating System</span>
          </div>
        </div>

        <nav className="nav-menu">
          <div className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
            <TrendingUp size={18} />
            <span>Dashboard</span>
          </div>
          <div className={`nav-item ${activeTab === 'patients' ? 'active' : ''}`} onClick={() => setActiveTab('patients')}>
            <Users size={18} />
            <span>Patients & EHR</span>
          </div>
          <div className={`nav-item ${activeTab === 'appointments' ? 'active' : ''}`} onClick={() => setActiveTab('appointments')}>
            <Calendar size={18} />
            <span>Appointments</span>
          </div>
          <div className={`nav-item ${activeTab === 'pharmacy' ? 'active' : ''}`} onClick={() => setActiveTab('pharmacy')}>
            <Pill size={18} />
            <span>Pharmacy & Stock</span>
          </div>
          <div className={`nav-item ${activeTab === 'lab' ? 'active' : ''}`} onClick={() => setActiveTab('lab')}>
            <TestTube size={18} />
            <span>Laboratory</span>
          </div>
          <div className={`nav-item ${activeTab === 'billing' ? 'active' : ''}`} onClick={() => setActiveTab('billing')}>
            <DollarSign size={18} />
            <span>Billing & Invoices</span>
          </div>
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="top-header">
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Outpatient Department (OPD) Dashboard</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ fontSize: '0.9rem', color: '#64748b' }}>Logged in as: <strong>Dr. Sarah Jenkins (CMO)</strong></span>
          </div>
        </header>

        <div className="page-wrapper">
          {/* Key Metrics Overview */}
          <div className="stats-grid">
            <div className="stat-card">
              <div>
                <span className="stat-label">Today's Appointments</span>
                <div className="stat-value">28</div>
              </div>
              <div className="stat-icon" style={{ background: '#dbeafe', color: '#2563eb' }}>
                <Calendar size={24} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <span className="stat-label">Active In-Queue</span>
                <div className="stat-value">12</div>
              </div>
              <div className="stat-icon" style={{ background: '#fef3c7', color: '#d97706' }}>
                <Clock size={24} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <span className="stat-label">Today's Revenue</span>
                <div className="stat-value">$3,420</div>
              </div>
              <div className="stat-icon" style={{ background: '#dcfce7', color: '#16a34a' }}>
                <DollarSign size={24} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <span className="stat-label">Low Stock Alerts</span>
                <div className="stat-value">3</div>
              </div>
              <div className="stat-icon" style={{ background: '#fee2e2', color: '#dc2626' }}>
                <AlertCircle size={24} />
              </div>
            </div>
          </div>

          {/* Real-time Patient Queue */}
          <div className="card-table-container">
            <div className="card-header">
              <h3 className="card-title">Live Clinic Queue & Patient Triage</h3>
              <button style={{ 
                background: '#2563eb', 
                color: 'white', 
                border: 'none', 
                padding: '0.5rem 1rem', 
                borderRadius: '8px', 
                display: 'flex', 
                alignItems: 'center', 
                gap: '0.5rem', 
                cursor: 'pointer',
                fontWeight: 500
              }}>
                <Plus size={16} /> New Walk-in Intake
              </button>
            </div>

            <table className="data-table">
              <thead>
                <tr>
                  <th>Time / Token</th>
                  <th>MRN</th>
                  <th>Patient Name</th>
                  <th>Age / Sex</th>
                  <th>Assigned Doctor</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {mockQueue.map((item) => (
                  <tr key={item.id}>
                    <td style={{ fontWeight: 600 }}>{item.time}</td>
                    <td style={{ color: '#64748b' }}>{item.mrn}</td>
                    <td style={{ fontWeight: 600 }}>{item.name}</td>
                    <td>{item.age} yrs / {item.gender}</td>
                    <td>{item.doctor}</td>
                    <td>
                      <span className={`badge ${
                        item.status === 'Completed' ? 'badge-success' : 
                        item.status === 'In Consultation' ? 'badge-info' : 'badge-warning'
                      }`}>
                        {item.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
