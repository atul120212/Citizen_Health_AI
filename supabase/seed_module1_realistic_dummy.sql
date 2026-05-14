-- Realistic-looking dummy data for Module 1.
-- Safe to run after creating the schema in Supabase SQL editor.
-- All names, phone numbers, and ABHA IDs below are fake demo values.

WITH inserted_locations AS (
    INSERT INTO locations (district_name, phc_name, village_taluka, geo_coordinates)
    VALUES
        (
            'Chennai',
            'T Nagar Urban Primary Health Centre',
            'T Nagar',
            'SRID=4326;POINT(80.2337 13.0418)'::extensions.geography
        ),
        (
            'Chennai',
            'Velachery Urban Primary Health Centre',
            'Velachery',
            'SRID=4326;POINT(80.2212 12.9756)'::extensions.geography
        ),
        (
            'Coimbatore',
            'Gandhipuram Urban Primary Health Centre',
            'Gandhipuram',
            'SRID=4326;POINT(76.9674 11.0176)'::extensions.geography
        ),
        (
            'Madurai',
            'Anna Nagar Primary Health Centre',
            'Anna Nagar',
            'SRID=4326;POINT(78.1483 9.9252)'::extensions.geography
        ),
        (
            'Bengaluru Urban',
            'Jayanagar Primary Health Centre',
            'Jayanagar',
            'SRID=4326;POINT(77.5838 12.9250)'::extensions.geography
        ),
        (
            'Bengaluru Urban',
            'Yelahanka Primary Health Centre',
            'Yelahanka',
            'SRID=4326;POINT(77.5963 13.1007)'::extensions.geography
        ),
        (
            'Mysuru',
            'Nazarbad Primary Health Centre',
            'Nazarbad',
            'SRID=4326;POINT(76.6624 12.3052)'::extensions.geography
        ),
        (
            'Dharwad',
            'Hubballi Urban Primary Health Centre',
            'Hubballi',
            'SRID=4326;POINT(75.1240 15.3647)'::extensions.geography
        )
    RETURNING id, district_name, phc_name
),
inserted_citizens AS (
    INSERT INTO citizens (
        abha_id,
        full_name,
        phone_number,
        preferred_language,
        location_id,
        ayushman_status,
        created_at
    )
    SELECT
        citizen.abha_id,
        citizen.full_name,
        citizen.phone_number,
        citizen.preferred_language,
        l.id,
        citizen.ayushman_status,
        NOW() - citizen.created_ago
    FROM inserted_locations l
    JOIN (
        VALUES
            ('T Nagar Urban Primary Health Centre', 'TA-DUMMY-000001', 'Meena Ravi', '9000001001', 'ta', TRUE, INTERVAL '42 days'),
            ('T Nagar Urban Primary Health Centre', 'TA-DUMMY-000002', 'Karthik Subramanian', '9000001002', 'ta', FALSE, INTERVAL '33 days'),
            ('Velachery Urban Primary Health Centre', 'TA-DUMMY-000003', 'Priya Narayanan', '9000001003', 'ta', TRUE, INTERVAL '21 days'),
            ('Velachery Urban Primary Health Centre', 'TA-DUMMY-000004', 'Arun Kumar', '9000001004', 'ta', FALSE, INTERVAL '12 days'),
            ('Gandhipuram Urban Primary Health Centre', 'TA-DUMMY-000005', 'Lakshmi Ganesan', '9000001005', 'ta', TRUE, INTERVAL '18 days'),
            ('Anna Nagar Primary Health Centre', 'TA-DUMMY-000006', 'Revathi Murugan', '9000001006', 'ta', TRUE, INTERVAL '9 days'),
            ('Jayanagar Primary Health Centre', 'KN-DUMMY-000001', 'Kavya Rao', '9000002001', 'kn', TRUE, INTERVAL '38 days'),
            ('Jayanagar Primary Health Centre', 'KN-DUMMY-000002', 'Ramesh Gowda', '9000002002', 'kn', FALSE, INTERVAL '30 days'),
            ('Yelahanka Primary Health Centre', 'KN-DUMMY-000003', 'Asha Hegde', '9000002003', 'kn', TRUE, INTERVAL '16 days'),
            ('Yelahanka Primary Health Centre', 'KN-DUMMY-000004', 'Manjunath Shetty', '9000002004', 'kn', FALSE, INTERVAL '13 days'),
            ('Nazarbad Primary Health Centre', 'KN-DUMMY-000005', 'Nandini Prakash', '9000002005', 'kn', TRUE, INTERVAL '8 days'),
            ('Hubballi Urban Primary Health Centre', 'KN-DUMMY-000006', 'Suresh Patil', '9000002006', 'kn', FALSE, INTERVAL '5 days')
    ) AS citizen(phc_name, abha_id, full_name, phone_number, preferred_language, ayushman_status, created_ago)
        ON citizen.phc_name = l.phc_name
    RETURNING id, full_name, phone_number, location_id, preferred_language
),
inserted_workers AS (
    INSERT INTO health_workers (name, role, location_id, phone_number)
    SELECT worker.name, worker.role, l.id, worker.phone_number
    FROM inserted_locations l
    JOIN (
        VALUES
            ('T Nagar Urban Primary Health Centre', 'Nurse Lakshmi', 'PHC Nurse', '9100001001'),
            ('T Nagar Urban Primary Health Centre', 'ASHA Selvi', 'ASHA', '9100001002'),
            ('Velachery Urban Primary Health Centre', 'Nurse Jayanthi', 'PHC Nurse', '9100001003'),
            ('Gandhipuram Urban Primary Health Centre', 'ASHA Kokila', 'ASHA', '9100001004'),
            ('Anna Nagar Primary Health Centre', 'Nurse Fathima', 'PHC Nurse', '9100001005'),
            ('Jayanagar Primary Health Centre', 'Nurse Shobha', 'PHC Nurse', '9100002001'),
            ('Jayanagar Primary Health Centre', 'ASHA Geetha', 'ASHA', '9100002002'),
            ('Yelahanka Primary Health Centre', 'Nurse Savitha', 'PHC Nurse', '9100002003'),
            ('Nazarbad Primary Health Centre', 'ASHA Roopa', 'ASHA', '9100002004'),
            ('Hubballi Urban Primary Health Centre', 'Nurse Rekha', 'PHC Nurse', '9100002005')
    ) AS worker(phc_name, name, role, phone_number)
        ON worker.phc_name = l.phc_name
    RETURNING id, name, role, location_id
),
inserted_interactions AS (
    INSERT INTO health_interactions (
        citizen_id,
        interaction_type,
        transcript_text,
        intent_detected,
        audio_url,
        status,
        created_at
    )
    SELECT
        c.id,
        interaction.interaction_type,
        interaction.transcript_text,
        interaction.intent_detected,
        interaction.audio_url,
        interaction.status,
        NOW() - interaction.created_ago
    FROM inserted_citizens c
    JOIN (
        VALUES
            ('9000001001', 'voice_call', 'எனக்கு நாளைக்கு டாக்டர் appointment book பண்ணணும்', 'appointment_booking', 'https://storage.example.com/demo/audio/ta-appointment-001.wav', 'needs_worker_followup', INTERVAL '2 days'),
            ('9000001002', 'voice_call', 'Ayushman Bharat eligibility எப்படி check பண்றது?', 'eligibility_check', 'https://storage.example.com/demo/audio/ta-eligibility-002.wav', 'completed', INTERVAL '7 days'),
            ('9000001003', 'voice_call', 'கர்ப்ப பரிசோதனை reminder set செய்யுங்கள்', 'maternal_health_reminder', 'https://storage.example.com/demo/audio/ta-maternal-003.wav', 'completed', INTERVAL '5 days'),
            ('9000001004', 'voice_call', 'Registration counter எங்க இருக்கு?', 'hospital_navigation', 'https://storage.example.com/demo/audio/ta-navigation-004.wav', 'completed', INTERVAL '1 day'),
            ('9000001005', 'voice_call', 'NHM immunisation programme details சொல்லுங்கள்', 'nhm_programme_query', 'https://storage.example.com/demo/audio/ta-nhm-005.wav', 'completed', INTERVAL '3 days'),
            ('9000001006', 'voice_call', 'குழந்தைக்கு தடுப்பூசி தேதி தெரிஞ்சுக்கணும்', 'nhm_programme_query', 'https://storage.example.com/demo/audio/ta-immunisation-006.wav', 'completed', INTERVAL '6 hours'),
            ('9000002001', 'voice_call', 'ನಾಳೆ ವೈದ್ಯರ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು', 'appointment_booking', 'https://storage.example.com/demo/audio/kn-appointment-001.wav', 'needs_worker_followup', INTERVAL '4 days'),
            ('9000002002', 'voice_call', 'CMCHIS eligibility check ಮಾಡಬೇಕು', 'eligibility_check', 'https://storage.example.com/demo/audio/kn-eligibility-002.wav', 'completed', INTERVAL '8 days'),
            ('9000002003', 'voice_call', 'ಗರ್ಭಿಣಿ ಆರೋಗ್ಯ ಪರಿಶೀಲನೆಗೆ reminder ಹಾಕಿ', 'maternal_health_reminder', 'https://storage.example.com/demo/audio/kn-maternal-003.wav', 'completed', INTERVAL '2 days'),
            ('9000002004', 'voice_call', 'PHC registration counter ಎಲ್ಲಿದೆ?', 'hospital_navigation', 'https://storage.example.com/demo/audio/kn-navigation-004.wav', 'completed', INTERVAL '12 hours'),
            ('9000002005', 'voice_call', 'NHM ತಾಯಂದಿರ ಆರೋಗ್ಯ ಕಾರ್ಯಕ್ರಮದ ಮಾಹಿತಿ ಬೇಕು', 'nhm_programme_query', 'https://storage.example.com/demo/audio/kn-nhm-005.wav', 'completed', INTERVAL '9 days'),
            ('9000002006', 'voice_call', 'ಹೃದಯ ನೋವು ಇದೆ, ಏನು ಮಾಡಬೇಕು?', 'emergency', 'https://storage.example.com/demo/audio/kn-emergency-006.wav', 'needs_worker_followup', INTERVAL '3 hours')
    ) AS interaction(phone_number, interaction_type, transcript_text, intent_detected, audio_url, status, created_ago)
        ON interaction.phone_number = c.phone_number
    RETURNING id
)
INSERT INTO appointments (
    citizen_id,
    worker_id,
    appointment_date,
    reason,
    status
)
SELECT
    c.id,
    w.id,
    appointment.appointment_date,
    appointment.reason,
    appointment.status
FROM inserted_citizens c
JOIN (
    VALUES
        ('9000001001', 'PHC Nurse', NOW() + INTERVAL '1 day 10 hours', 'General OP consultation for fever and body pain', 'scheduled'),
        ('9000001003', 'PHC Nurse', NOW() + INTERVAL '3 days 9 hours', 'ANC visit and haemoglobin check', 'scheduled'),
        ('9000001005', 'ASHA', NOW() - INTERVAL '5 days', 'Immunisation counselling follow-up', 'visited'),
        ('9000001006', 'PHC Nurse', NOW() + INTERVAL '2 days 11 hours', 'Child vaccination due-date verification', 'scheduled'),
        ('9000002001', 'PHC Nurse', NOW() + INTERVAL '1 day 11 hours', 'General OP consultation for cough and fever', 'scheduled'),
        ('9000002003', 'PHC Nurse', NOW() + INTERVAL '4 days 10 hours', 'Pregnancy ANC follow-up', 'scheduled'),
        ('9000002005', 'ASHA', NOW() - INTERVAL '2 days', 'NHM maternal health programme counselling', 'visited'),
        ('9000002006', 'PHC Nurse', NOW(), 'Urgent follow-up requested after emergency symptom call', 'scheduled')
) AS appointment(phone_number, worker_role, appointment_date, reason, status)
    ON appointment.phone_number = c.phone_number
JOIN inserted_workers w
    ON w.location_id = c.location_id
   AND w.role = appointment.worker_role;
