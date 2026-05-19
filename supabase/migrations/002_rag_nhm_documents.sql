-- ============================================================
-- Migration: Add RAG knowledge base table (nhm_documents)
-- Requires: pgvector extension enabled in Supabase
-- ============================================================

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- NHM knowledge documents for RAG retrieval
CREATE TABLE IF NOT EXISTS nhm_documents (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    category        TEXT NOT NULL,   -- 'scheme', 'drug', 'navigation', 'faq', 'phc_service'
    language_code   TEXT NOT NULL DEFAULT 'en-IN',
    source          TEXT,            -- URL or reference
    embedding       vector(1024),    -- Sarvam text-embedding-007 dimension
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (title, language_code)
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS nhm_documents_embedding_idx
    ON nhm_documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Seed NHM knowledge base
INSERT INTO nhm_documents (title, content, category, language_code, source) VALUES
(
    'Ayushman Bharat PM-JAY Eligibility',
    'Ayushman Bharat Pradhan Mantri Jan Arogya Yojana (PM-JAY) provides health insurance cover of Rs 5 lakh per family per year. Eligibility is based on SECC 2011 database. Beneficiaries include rural families based on deprivation criteria and occupational categories of urban workers. No premium to be paid by beneficiaries. Coverage includes pre and post hospitalization. ABHA card is required for identification.',
    'scheme',
    'en-IN',
    'https://pmjay.gov.in'
),
(
    'CMCHIS Tamil Nadu Eligibility',
    'Chief Minister Comprehensive Health Insurance Scheme (CMCHIS) is a Tamil Nadu government scheme providing health insurance of Rs 5 lakh per family per year. Eligible if annual family income is below Rs 72,000. Apply at Aadhaar Seva Kendrams or Government hospitals. Bring income certificate, Aadhaar card, and ration card.',
    'scheme',
    'en-IN',
    'https://www.cmchistn.com'
),
(
    'ANC Visit Schedule',
    'Antenatal Care (ANC) visits recommended schedule: First visit within 12 weeks of pregnancy. Second visit between 14-26 weeks. Third visit between 28-34 weeks. Fourth visit between 36 weeks to delivery. Each visit includes: weight measurement, blood pressure, urine test, blood test (hemoglobin, blood group), ultrasound as needed, tetanus vaccination (TT), IFA tablets distribution, and counseling.',
    'faq',
    'en-IN',
    'https://nhm.gov.in'
),
(
    'PHC Navigation Guide',
    'At Primary Health Centre (PHC): Registration Counter is at the Ground Floor entrance. OPD (General) is on Ground Floor Room 1. Maternal and Child Health (MCH) is on Ground Floor Room 3. Laboratory is in the basement. Pharmacy is next to Registration. Emergency/Casualty is at the main entrance. Specialists visit on Tuesdays and Thursdays. Timings: 9 AM to 5 PM Monday to Saturday.',
    'navigation',
    'en-IN',
    NULL
),
(
    'National Health Mission Programmes',
    'NHM programmes in India include: RMNCH+A (Reproductive, Maternal, Newborn, Child, and Adolescent Health), Janani Suraksha Yojana (JSY) for institutional delivery cash incentive, JSSK (free drugs and diagnostics for pregnant women), Rashtriya Kishor Swasthya Karyakram (RKSK) for adolescent health, National Ambulance Services (108), Free Medicines Scheme, and ASHA incentive programmes.',
    'faq',
    'en-IN',
    'https://nhm.gov.in'
),
(
    'Emergency Contact Numbers India',
    'Emergency numbers: Ambulance 108 (free, 24x7), Police 100, Fire 101, Women helpline 1091, ASHA worker contact via local PHC, National Health Helpline 1800-180-1104. For cardiac/stroke emergencies: call 108 immediately and do not drive the patient yourself. Golden hour for heart attack treatment is critical.',
    'faq',
    'en-IN',
    NULL
)
ON CONFLICT (title, language_code) DO NOTHING;

-- Tamil versions of key documents
INSERT INTO nhm_documents (title, content, category, language_code, source) VALUES
(
    'Ayushman Bharat PM-JAY தகுதி',
    'ஆயுஷ்மான் பாரத் PM-JAY திட்டம் ஒவ்வொரு குடும்பத்திற்கும் ஆண்டுக்கு ரூ.5 லட்சம் வரை சுகாதார காப்பீடு வழங்குகிறது. SECC 2011 தரவுத்தளத்தின் அடிப்படையில் தகுதி தீர்மானிக்கப்படும். பயனாளிகள் பிரீமியம் செலுத்த வேண்டியதில்லை. ABHA அட்டை அவசியம்.',
    'scheme',
    'ta-IN',
    'https://pmjay.gov.in'
),
(
    'ANC வருகை அட்டவணை',
    'கர்ப்பகால பரிசோதனை (ANC) வருகைகள்: முதல் வருகை 12 வாரங்களுக்குள். இரண்டாம் வருகை 14-26 வாரங்களில். மூன்றாம் வருகை 28-34 வாரங்களில். நான்காம் வருகை 36 வாரங்கள் முதல் பிரசவம் வரை. ஒவ்வொரு வருகையிலும் எடை, ரத்த அழுத்தம், சிறுநீர் மற்றும் ரத்த பரிசோதனை, TT தடுப்பூசி மற்றும் IFA மாத்திரைகள் வழங்கப்படும்.',
    'faq',
    'ta-IN',
    'https://nhm.gov.in'
)
ON CONFLICT (title, language_code) DO NOTHING;

-- Hindi version
INSERT INTO nhm_documents (title, content, category, language_code, source) VALUES
(
    'आयुष्मान भारत पात्रता',
    'आयुष्मान भारत PM-JAY योजना प्रति परिवार प्रति वर्ष 5 लाख रुपये का स्वास्थ्य बीमा प्रदान करती है। SECC 2011 डेटाबेस के आधार पर पात्रता निर्धारित होती है। लाभार्थियों को कोई प्रीमियम नहीं देना होता। पहचान के लिए ABHA कार्ड आवश्यक है।',
    'scheme',
    'hi-IN',
    'https://pmjay.gov.in'
)
ON CONFLICT (title, language_code) DO NOTHING;
