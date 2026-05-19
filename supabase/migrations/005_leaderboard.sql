-- Migration 005: Leaderboard & Incentives
-- Links records to workers for gamification

ALTER TABLE health_worker_records 
ADD COLUMN IF NOT EXISTS worker_id UUID REFERENCES health_workers(id);

-- Create a view for easy leaderboard calculation
CREATE OR REPLACE VIEW worker_performance AS
SELECT 
    hw.id as worker_id,
    hw.name,
    hw.role,
    l.district_name,
    COUNT(hwr.id) as records_count,
    COUNT(DISTINCT hwr.patient_name) as unique_patients,
    (COUNT(hwr.id) * 10) + (COUNT(DISTINCT hwr.patient_name) * 5) as performance_score
FROM health_workers hw
JOIN locations l ON l.id = hw.location_id
LEFT JOIN health_worker_records hwr ON hwr.worker_id = hw.id
GROUP BY hw.id, hw.name, hw.role, l.district_name;
