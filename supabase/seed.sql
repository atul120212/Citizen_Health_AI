WITH location_rows AS (
    INSERT INTO locations (district_name, phc_name, village_taluka, geo_coordinates)
    VALUES
        ('Chennai', 'T Nagar Urban PHC', 'T Nagar', ST_SetSRID(ST_MakePoint(80.2337, 13.0418), 4326)::geography),
        ('Bengaluru Urban', 'Jayanagar PHC', 'Jayanagar', ST_SetSRID(ST_MakePoint(77.5838, 12.9250), 4326)::geography)
    RETURNING id, district_name
),
citizen_rows AS (
    INSERT INTO citizens (abha_id, full_name, phone_number, preferred_language, location_id, ayushman_status)
    SELECT
        CASE WHEN district_name = 'Chennai' THEN '91-1234-5678-9012' ELSE '91-5555-2222-1111' END,
        CASE WHEN district_name = 'Chennai' THEN 'Meena Ravi' ELSE 'Kavya Rao' END,
        CASE WHEN district_name = 'Chennai' THEN '9000000001' ELSE '9000000002' END,
        CASE WHEN district_name = 'Chennai' THEN 'ta' ELSE 'kn' END,
        id,
        district_name = 'Bengaluru Urban'
    FROM location_rows
    RETURNING id, location_id
)
INSERT INTO health_workers (name, role, location_id, phone_number)
SELECT
    CASE WHEN l.district_name = 'Chennai' THEN 'Nurse Lakshmi' ELSE 'ASHA Shobha' END,
    CASE WHEN l.district_name = 'Chennai' THEN 'PHC Nurse' ELSE 'ASHA' END,
    l.id,
    CASE WHEN l.district_name = 'Chennai' THEN '9100000001' ELSE '9100000002' END
FROM locations l
WHERE l.district_name IN ('Chennai', 'Bengaluru Urban')
ON CONFLICT DO NOTHING;

INSERT INTO hospital_departments (location_id, department_name, floor_label, room_label, services, open_hours)
SELECT id, 'Registration Counter', 'Ground floor', 'Room 1', 'OP registration, ABHA support, appointment desk', '08:00-14:00'
FROM locations
WHERE phc_name IN ('T Nagar Urban PHC', 'Jayanagar PHC')
ON CONFLICT DO NOTHING;

INSERT INTO hospital_departments (location_id, department_name, floor_label, room_label, services, open_hours)
SELECT id, 'Maternal and Child Health', 'Ground floor', 'Room 4', 'ANC checkups, immunisation, IFA counselling', '09:00-13:00'
FROM locations
WHERE phc_name IN ('T Nagar Urban PHC', 'Jayanagar PHC')
ON CONFLICT DO NOTHING;

INSERT INTO nhm_programme_faqs (programme_name, language_code, question, answer)
VALUES
    ('Janani Suraksha Yojana', 'en-IN', 'Who can ask about JSY?', 'Pregnant women can ask the PHC or ASHA worker about JSY registration, documents, and follow-up visits.'),
    ('Janani Suraksha Yojana', 'ta-IN', 'JSY பற்றி யார் கேட்கலாம்?', 'கர்ப்பிணி பெண்கள் JSY பதிவு, ஆவணங்கள் மற்றும் பின்தொடர் பரிசோதனை பற்றி PHC அல்லது ASHA பணியாளரிடம் கேட்கலாம்.'),
    ('Janani Suraksha Yojana', 'kn-IN', 'JSY ಬಗ್ಗೆ ಯಾರು ಕೇಳಬಹುದು?', 'ಗರ್ಭಿಣಿಯರು JSY ನೋಂದಣಿ, ದಾಖಲೆಗಳು ಮತ್ತು ಅನುಸರಣೆ ಭೇಟಿಗಳ ಬಗ್ಗೆ PHC ಅಥವಾ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಕೇಳಬಹುದು.'),
    ('Routine Immunisation', 'en-IN', 'Where can I get immunisation details?', 'Your nearest PHC or ASHA worker can confirm vaccine due dates and session days.'),
    ('Routine Immunisation', 'ta-IN', 'தடுப்பூசி விவரங்கள் எங்கு கிடைக்கும்?', 'அருகிலுள்ள PHC அல்லது ASHA பணியாளர் தடுப்பூசி தேதிகள் மற்றும் முகாம் நாட்களை உறுதிப்படுத்துவார்.'),
    ('Routine Immunisation', 'kn-IN', 'ಲಸಿಕೆ ವಿವರಗಳು ಎಲ್ಲಿ ಸಿಗುತ್ತವೆ?', 'ನಿಮ್ಮ ಸಮೀಪದ PHC ಅಥವಾ ASHA ಕಾರ್ಯಕರ್ತರು ಲಸಿಕೆ ದಿನಾಂಕಗಳು ಮತ್ತು ಶಿಬಿರದ ದಿನಗಳನ್ನು ದೃಢಪಡಿಸಬಹುದು.')
ON CONFLICT DO NOTHING;
