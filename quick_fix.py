import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='compliance_db',
    user='postgres',
    password='nabilah',
    port='5432',
    connect_timeout=5
)
cur = conn.cursor()

try:
    print('Creating sequence...')
    cur.execute('CREATE SEQUENCE IF NOT EXISTS defects_id_seq')
    
    print('Setting column default...')
    cur.execute('ALTER TABLE defects ALTER COLUMN id SET DEFAULT nextval(\'defects_id_seq\')')
    
    print('Setting sequence owner...')
    cur.execute('ALTER SEQUENCE defects_id_seq OWNED BY defects.id')
    
    print('Setting sequence value...')
    cur.execute('SELECT setval(\'defects_id_seq\', COALESCE((SELECT MAX(id) FROM defects), 0) + 1)')
    
    conn.commit()
    print('✅ Defects table id sequence fixed successfully!')
    
except Exception as e:
    conn.rollback()
    print(f'❌ Error: {e}')
finally:
    cur.close()
    conn.close()
