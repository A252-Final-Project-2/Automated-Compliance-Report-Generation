import os
import sys
try:
    import psycopg2
except Exception as e:
    print('MISSING_PSYCOG', e)
    sys.exit(3)
from dotenv import load_dotenv
load_dotenv(r"app/module3/.env")
print('ENV:', os.getenv('DB_HOST'), os.getenv('DB_PORT'), os.getenv('DB_NAME'), os.getenv('DB_USER'))
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        connect_timeout=5,
    )
    print('CONNECTED')
    conn.close()
except Exception as e:
    print('ERROR', type(e).__name__, str(e))
    sys.exit(2)
