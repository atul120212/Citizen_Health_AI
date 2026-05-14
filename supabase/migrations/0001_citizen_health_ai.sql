CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;

-- Shared across all modules
CREATE TABLE IF NOT EXISTS locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    district_name VARCHAR(100),
    phc_name VARCHAR(100),
    village_taluka VARCHAR(100),
    geo_coordinates GEOGRAPHY(POINT)
);

CREATE TABLE IF NOT EXISTS citizens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    abha_id VARCHAR(20) UNIQUE,
    full_name VARCHAR(255),
    phone_number VARCHAR(15) UNIQUE,
    preferred_language VARCHAR(10),
    location_id UUID REFERENCES locations(id),
    ayushman_status BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS health_workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    role VARCHAR(50),
    location_id UUID REFERENCES locations(id),
    phone_number VARCHAR(15)
);

-- Module 1 creates these; Module 2 can read/update them.
CREATE TABLE IF NOT EXISTS health_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID REFERENCES citizens(id),
    interaction_type VARCHAR(50),
    transcript_text TEXT,
    intent_detected VARCHAR(100),
    audio_url TEXT,
    status VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID REFERENCES citizens(id),
    worker_id UUID REFERENCES health_workers(id),
    appointment_date TIMESTAMP WITH TIME ZONE,
    reason TEXT,
    status VARCHAR(20)
);

-- Module 1 support tables.
CREATE TABLE IF NOT EXISTS hospital_departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID REFERENCES locations(id),
    department_name VARCHAR(120) NOT NULL,
    floor_label VARCHAR(60),
    room_label VARCHAR(60),
    services TEXT,
    open_hours VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS maternal_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID REFERENCES citizens(id),
    reminder_type VARCHAR(50) NOT NULL,
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nhm_programme_faqs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    programme_name VARCHAR(120) NOT NULL,
    language_code VARCHAR(10) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_locations_district ON locations (district_name);
CREATE INDEX IF NOT EXISTS idx_citizens_phone ON citizens (phone_number);
CREATE INDEX IF NOT EXISTS idx_citizens_location ON citizens (location_id);
CREATE INDEX IF NOT EXISTS idx_workers_location ON health_workers (location_id);
CREATE INDEX IF NOT EXISTS idx_interactions_citizen_created ON health_interactions (citizen_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_intent ON health_interactions (intent_detected);
CREATE INDEX IF NOT EXISTS idx_appointments_citizen_date ON appointments (citizen_id, appointment_date DESC);
CREATE INDEX IF NOT EXISTS idx_maternal_reminders_citizen_due ON maternal_reminders (citizen_id, due_date);
CREATE INDEX IF NOT EXISTS idx_departments_location ON hospital_departments (location_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'health_interactions_status_check') THEN
        ALTER TABLE health_interactions
            ADD CONSTRAINT health_interactions_status_check
            CHECK (status IN ('completed', 'needs_worker_followup'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'appointments_status_check') THEN
        ALTER TABLE appointments
            ADD CONSTRAINT appointments_status_check
            CHECK (status IN ('scheduled', 'visited', 'missed', 'cancelled'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'maternal_reminders_status_check') THEN
        ALTER TABLE maternal_reminders
            ADD CONSTRAINT maternal_reminders_status_check
            CHECK (status IN ('pending', 'sent', 'completed', 'missed'));
    END IF;
END $$;
