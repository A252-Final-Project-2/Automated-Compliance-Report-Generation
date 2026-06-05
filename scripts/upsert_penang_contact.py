#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.abspath('.'))
try:
    from app.module3.database.db import get_connection
    from app.module3.encryption_utils import encrypt_text as _encrypt_text, is_encrypted_text as _is_encrypted_text
except Exception:
    from database.db import get_connection
    from encryption_utils import encrypt_text as _encrypt_text, is_encrypted_text as _is_encrypted_text

# Provided contact data
contact = {
    'id': 7,
    'developer_id': 5,  # map to daniellee's user id
    'state_name': 'Pulau Pinang',
    'person_in_charge': 'Daniel Lee',
    'phone_number': '014-9988776',
    'email': 'penang@skyline.com',
    'office_address': "No.20 Lebuh Pantai,\n10300 George Town,\nPulau Pinang",
}

conn = get_connection()
cur = conn.cursor()
try:
    # Ensure developer exists
    cur.execute("SELECT id FROM users WHERE id = %s AND role = 'Developer'", (contact['developer_id'],))
    if not cur.fetchone():
        print('Developer user id not found; aborting')
        sys.exit(1)

    # Upsert developer_contacts using provided id
    # Encrypt sensitive fields using project's encryption helper
    enc_person = _encrypt_text(contact['person_in_charge']) if contact['person_in_charge'] else None
    enc_phone = _encrypt_text(contact['phone_number']) if contact['phone_number'] else None
    enc_email = _encrypt_text(contact['email']) if contact['email'] else None
    enc_office = _encrypt_text(contact['office_address']) if contact['office_address'] else None

    cur.execute(
        """
        INSERT INTO developer_contacts (id, developer_id, state_name, person_in_charge, phone_number, email, office_address, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            developer_id = EXCLUDED.developer_id,
            state_name = EXCLUDED.state_name,
            person_in_charge = EXCLUDED.person_in_charge,
            phone_number = EXCLUDED.phone_number,
            email = EXCLUDED.email,
            office_address = EXCLUDED.office_address
        """,
        (
            contact['id'], contact['developer_id'], contact['state_name'],
            enc_person, enc_phone, enc_email, enc_office
        )
    )
    conn.commit()
    print('Upserted developer_contacts id=%s for developer_id=%s' % (contact['id'], contact['developer_id']))
finally:
    cur.close()
    conn.close()
