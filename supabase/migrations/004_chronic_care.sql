-- Migration 004: Chronic Care & Adherence
-- Supports NCD tracking and medicine reminders

-- Table for tracking patient vitals (BP, Sugar, Weight, etc.)
CREATE TABLE IF NOT EXISTS patient_vitals_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID NOT NULL REFERENCES citizens(id) ON DELETE CASCADE,
    vital_type VARCHAR(50) NOT NULL, -- 'bp_systolic', 'bp_diastolic', 'blood_sugar', 'weight', 'heart_rate'
    value DECIMAL(10, 2) NOT NULL,
    unit VARCHAR(20),
    measured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    source VARCHAR(50) DEFAULT 'voice_ai', -- 'voice_ai', 'manual_entry', 'device'
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for tracking medication schedules and adherence
CREATE TABLE IF NOT EXISTS medication_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID NOT NULL REFERENCES citizens(id) ON DELETE CASCADE,
    medication_name VARCHAR(255) NOT NULL,
    dosage VARCHAR(100),
    frequency VARCHAR(100), -- 'once_daily', 'twice_daily', etc.
    prescribed_by VARCHAR(255),
    start_date DATE,
    end_date DATE,
    last_taken_at TIMESTAMP WITH TIME ZONE,
    adherence_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_vitals_citizen_date ON patient_vitals_log(citizen_id, measured_at);
CREATE INDEX IF NOT EXISTS idx_meds_citizen ON medication_schedules(citizen_id);
