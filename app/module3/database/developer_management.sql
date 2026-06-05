-- =========================================
-- MAIN DEVELOPER COMPANY
-- =========================================

CREATE TABLE IF NOT EXISTS developers (
    id SERIAL PRIMARY KEY,

    company_name TEXT NOT NULL UNIQUE,

    registration_number TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- =========================================
-- DEVELOPER PERSON IN CHARGE BY STATE
-- =========================================

CREATE TABLE IF NOT EXISTS developer_contacts (
    id SERIAL PRIMARY KEY,

    developer_id INTEGER NOT NULL
        REFERENCES developers(id)
        ON DELETE CASCADE,

    state_name TEXT NOT NULL,

    person_in_charge TEXT NOT NULL,

    phone_number TEXT,

    email TEXT,

    office_address TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- =========================================
-- PROJECTS
-- =========================================

CREATE TABLE IF NOT EXISTS developer_projects (

    id SERIAL PRIMARY KEY,

    developer_id INTEGER NOT NULL
        REFERENCES developers(id)
        ON DELETE CASCADE,

    project_name TEXT NOT NULL UNIQUE,

    state_name TEXT NOT NULL,

    property_address TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- =========================================
-- PROJECT UNITS
-- =========================================

CREATE TABLE IF NOT EXISTS project_units (

    id SERIAL PRIMARY KEY,

    project_id INTEGER NOT NULL
        REFERENCES developer_projects(id)
        ON DELETE CASCADE,

    unit_number TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT NOW()
);

-- =========================================
-- DEVELOPER USER PROJECT ACCESS
-- =========================================

CREATE TABLE IF NOT EXISTS developer_project_access (

    developer_user_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    project_id INTEGER NOT NULL
        REFERENCES developer_projects(id)
        ON DELETE CASCADE,

    created_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (developer_user_id, project_id)
);

-- =========================================
-- INSERT 1 COMPANY ONLY
-- =========================================

INSERT INTO developers
(
    company_name,
    registration_number
)
VALUES
(
    'Skyline Development Sdn Bhd',
    '202301001111'
)
ON CONFLICT (company_name) DO NOTHING;

-- =========================================
-- PERSON IN CHARGE FOR EACH STATE
-- =========================================

INSERT INTO developer_contacts
(
    developer_id,
    state_name,
    person_in_charge,
    phone_number,
    email,
    office_address
)
VALUES

(
    1,
    'Johor',
    'Kelvin Tan',
    '018-6677889',
    'johor@skyline.com',
    'No.15 Jalan Austin Perdana,
    81100 Johor Bahru,
    Johor'
),

(
    1,
    'Kedah',
    'Muhammad Amir',
    '012-3456789',
    'kedah@skyline.com',
    'No.25 Jalan Sultanah,
    05350 Alor Setar,
    Kedah'
),

(
    1,
    'Kelantan',
    'Ahmad Faiz',
    '012-7788990',
    'kelantan@skyline.com',
    'No.8 Jalan Pengkalan Chepa,
    15400 Kota Bharu,
    Kelantan'
),

(
    1,
    'Melaka',
    'Nur Izzati',
    '013-6677881',
    'melaka@skyline.com',
    'No.18 Jalan Hang Tuah,
    75300 Melaka Tengah,
    Melaka'
),

(
    1,
    'Negeri Sembilan',
    'Syafiq Roslan',
    '014-5566778',
    'ns@skyline.com',
    'No.7 Jalan Dato Bandar Tunggal,
    70000 Seremban,
    Negeri Sembilan'
),

(
    1,
    'Pahang',
    'Aiman Hakimi',
    '016-9988771',
    'pahang@skyline.com',
    'No.11 Jalan Beserah,
    25300 Kuantan,
    Pahang'
),

(
    1,
    'Pulau Pinang',
    'Daniel Lee',
    '014-9988776',
    'penang@skyline.com',
    'No.20 Lebuh Pantai,
    10300 George Town,
    Pulau Pinang'
),

(
    1,
    'Perak',
    'Aina Sofea',
    '017-4455667',
    'perak@skyline.com',
    'No.9 Jalan Sultan Idris Shah,
    30000 Ipoh,
    Perak'
),

(
    1,
    'Perlis',
    'Nur Syafiqah',
    '013-2233445',
    'perlis@skyline.com',
    'No.3 Jalan Kangar Jaya,
    01000 Kangar,
    Perlis'
),

(
    1,
    'Sabah',
    'Siti Khadijah',
    '016-1234567',
    'sabah@skyline.com',
    'No.12 Jalan Lintas,
    88300 Kota Kinabalu,
    Sabah'
),

(
    1,
    'Sarawak',
    'Farhan Hakim',
    '019-8877665',
    'sarawak@skyline.com',
    'No.5 Jalan Satok,
    93400 Kuching,
    Sarawak'
),

(
    1,
    'Selangor',
    'Nurul Aisyah',
    '011-3344556',
    'selangor@skyline.com',
    'No.12 Jalan Putra Heights,
    40100 Shah Alam,
    Selangor'
),

(
    1,
    'Terengganu',
    'Nur Alya',
    '017-2233441',
    'terengganu@skyline.com',
    'No.6 Jalan Sultan Zainal Abidin,
    20000 Kuala Terengganu,
    Terengganu'
),

(
    1,
    'Kuala Lumpur',
    'Daniel Wong',
    '018-3344552',
    'kl@skyline.com',
    'No.30 Jalan Genting Klang,
    53300 Setapak,
    Kuala Lumpur'
),

(
    1,
    'Labuan',
    'Faris Imran',
    '019-4455662',
    'labuan@skyline.com',
    'No.2 Jalan Merdeka,
    87000 Labuan'
),

(
    1,
    'Putrajaya',
    'Siti Nurul',
    '011-5566772',
    'putrajaya@skyline.com',
    'No.1 Persiaran Perdana,
    62000 Putrajaya'
);

-- =========================================
-- PROJECTS ACROSS MALAYSIA
-- =========================================

INSERT INTO developer_projects
(
    developer_id,
    project_name,
    state_name,
    property_address
)
VALUES

(
    1,
    'Skyline Residence Johor',
    'Johor',
    'No.21 Jalan Austin Perdana,
    81100 Johor Bahru,
    Johor'
),

(
    1,
    'Skyline Kedah Residence',
    'Kedah',
    'No.18 Jalan Sultanah,
    05350 Alor Setar,
    Kedah'
),

(
    1,
    'Skyline Kelantan Heights',
    'Kelantan',
    'No.6 Jalan Pengkalan Chepa,
    15400 Kota Bharu,
    Kelantan'
),

(
    1,
    'Skyline Melaka Bay',
    'Melaka',
    'No.12 Jalan Hang Tuah,
    75300 Melaka Tengah,
    Melaka'
),

(
    1,
    'Skyline Seremban Vista',
    'Negeri Sembilan',
    'No.9 Jalan Dato Bandar Tunggal,
    70000 Seremban,
    Negeri Sembilan'
),

(
    1,
    'Skyline Kuantan Residency',
    'Pahang',
    'No.5 Jalan Beserah,
    25300 Kuantan,
    Pahang'
),

(
    1,
    'Skyline Pulau Pinang Central',
    'Pulau Pinang',
    'No.30 Lebuh Pantai,
    10300 George Town,
    Pulau Pinang'
),

(
    1,
    'Skyline Ipoh Residence',
    'Perak',
    'No.11 Jalan Sultan Idris Shah,
    30000 Ipoh,
    Perak'
),

(
    1,
    'Skyline Kangar Harmoni',
    'Perlis',
    'No.4 Jalan Kangar Jaya,
    01000 Kangar,
    Perlis'
),

(
    1,
    'Skyline Sabah Heights',
    'Sabah',
    'No.15 Jalan Lintas,
    88300 Kota Kinabalu,
    Sabah'
),

(
    1,
    'Skyline Kuching Sentral',
    'Sarawak',
    'No.8 Jalan Satok,
    93400 Kuching,
    Sarawak'
),

(
    1,
    'Skyline Selangor Residence',
    'Selangor',
    'No.10 Jalan Setia Alam,
    40170 Shah Alam,
    Selangor'
),

(
    1,
    'Skyline Terengganu Bay',
    'Terengganu',
    'No.2 Jalan Sultan Zainal Abidin,
    20000 Kuala Terengganu,
    Terengganu'
),

(
    1,
    'Skyline KL Sentral',
    'Federal Territory of Kuala Lumpur',
    'No.50 Jalan Genting Klang,
    53300 Setapak,
    Kuala Lumpur'
),

(
    1,
    'Skyline Labuan Point',
    'Federal Territory of Labuan',
    'No.1 Jalan Merdeka,
    87000 Labuan'
),

(
    1,
    'Skyline Putrajaya Residence',
    'Federal Territory of Putrajaya',
    'No.3 Persiaran Perdana,
    62000 Putrajaya'

),

(
    1,
    'Others / Unassigned',
    'Others',
    'Units not listed under state-specific Skyline projects'
);

INSERT INTO project_units
(project_id, unit_number)
VALUES

-- JOHOR
(1,'J-01-01'),
(1,'J-01-02'),
(1,'J-02-01'),
(1,'J-03-03'),

-- KEDAH
(2,'KDH-01-01'),
(2,'KDH-02-02'),
(2,'KDH-03-01'),
(2,'KDH-05-03'),

-- KELANTAN
(3,'KLT-01-02'),
(3,'KLT-02-01'),
(3,'KLT-04-03'),
(3,'KLT-06-01'),

-- MELAKA
(4,'MLK-01-01'),
(4,'MLK-03-02'),
(4,'MLK-04-01'),
(4,'MLK-08-03'),

-- NEGERI SEMBILAN
(5,'NS-02-08'),
(5,'NS-03-01'),
(5,'NS-05-02'),
(5,'NS-07-01'),

-- PAHANG
(6,'PHG-01-01'),
(6,'PHG-02-03'),
(6,'PHG-07-01'),
(6,'PHG-11-02'),

-- PENANG
(7,'PNG-01-02'),
(7,'PNG-04-01'),
(7,'PNG-08-03'),
(7,'PNG-09-01'),

-- PERAK
(8,'PRK-01-01'),
(8,'PRK-03-02'),
(8,'PRK-05-01'),
(8,'PRK-06-04'),

-- PERLIS
(9,'PLS-01-02'),
(9,'PLS-02-01'),
(9,'PLS-03-03'),
(9,'PLS-04-01'),

-- SABAH
(10,'SBH-02-01'),
(10,'SBH-04-02'),
(10,'SBH-08-03'),
(10,'SBH-12-01'),

-- SARAWAK
(11,'SWK-01-01'),
(11,'SWK-03-02'),
(11,'SWK-05-01'),
(11,'SWK-07-03'),

-- SELANGOR
(12,'SGR-01-01'),
(12,'SGR-05-02'),
(12,'SGR-10-01'),
(12,'SGR-15-02'),

-- TERENGGANU
(13,'TRG-01-01'),
(13,'TRG-02-03'),
(13,'TRG-03-02'),
(13,'TRG-04-06'),

-- KUALA LUMPUR
(14,'KL-01-01'),
(14,'KL-08-03'),
(14,'KL-12-02'),
(14,'KL-20-01'),

-- LABUAN
(15,'LBN-01-01'),
(15,'LBN-02-02'),
(15,'LBN-03-02'),
(15,'LBN-04-01'),

-- PUTRAJAYA
(16,'PJY-01-01'),
(16,'PJY-03-03'),
(16,'PJY-06-01'),
(16,'PJY-10-05');
