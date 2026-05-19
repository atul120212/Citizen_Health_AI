-- Migration 003: System fixes and new tables

-- 1. Table for serverless session state
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    service_type VARCHAR(50) NOT NULL, -- 'citizen' or 'health_worker'
    history JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Table for health worker records missing from initial migration
CREATE TABLE IF NOT EXISTS health_worker_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_name VARCHAR(255),
    age INT,
    gender VARCHAR(20),
    phone_number VARCHAR(15),
    chief_complaint TEXT,
    bp_systolic INT,
    bp_diastolic INT,
    weight_kg NUMERIC(5,2),
    hemoglobin NUMERIC(5,2),
    gestational_age_weeks INT,
    symptoms JSONB,
    diagnosis TEXT,
    treatment_given TEXT,
    next_visit_date DATE,
    referred BOOLEAN DEFAULT FALSE,
    referral_to TEXT,
    notes TEXT,
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
