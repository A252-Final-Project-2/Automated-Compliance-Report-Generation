#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.abspath('.'))
try:
    from app.module3.database.db import get_connection
    from app.module3.encryption_utils import encrypt_text as _encrypt_text
except Exception:
    from database.db import get_connection
    from encryption_utils import encrypt_text as _encrypt_text

contact = {
    'respondent_id': 5,
    'company_name': 'Skyline Development Sdn Bhd',
    'person_in_charge': 'Daniel Lee',
    'registration_number': None,
    'email': 'penang@skyline.com',
    'phone_number': '014-9988776',
    'address': 'No.20 Lebuh Pantai,\n10300 George Town,\nPulau Pinang'
}

conn = get_connection()
cur = conn.cursor()
try:
    # Upsert into report_respondent_profile
    enc_company = _encrypt_text(contact['company_name']) if contact['company_name'] else None
    enc_pic = _encrypt_text(contact['person_in_charge']) if contact['person_in_charge'] else None
    enc_reg = _encrypt_text(contact['registration_number']) if contact['registration_number'] else None
    enc_email = _encrypt_text(contact['email']) if contact['email'] else None
    enc_phone = _encrypt_text(contact['phone_number']) if contact['phone_number'] else None
    enc_addr = _encrypt_text(contact['address']) if contact['address'] else None

    cur.execute(
        """
        INSERT INTO report_respondent_profile (respondent_id, company_name, person_in_charge, registration_number, email, phone_number, address, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (respondent_id) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            person_in_charge = EXCLUDED.person_in_charge,
            registration_number = EXCLUDED.registration_number,
            email = EXCLUDED.email,
            phone_number = EXCLUDED.phone_number,
            address = EXCLUDED.address,
            updated_at = EXCLUDED.updated_at
        """,
        (
            contact['respondent_id'], enc_company, enc_pic, enc_reg, enc_email, enc_phone, enc_addr
        )
    )
    conn.commit()
    print('OK: upserted report_respondent_profile for respondent_id=%s' % contact['respondent_id'])
finally:
    cur.close()
    conn.close()
