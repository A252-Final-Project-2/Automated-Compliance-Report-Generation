from db import get_connection

try:
    conn = get_connection()
    print("✅ Connected to database!")
    conn.close()
except Exception as e:
    error_text = str(e)
    print("❌ Error:", error_text)

    if "DB_PASSWORD is not set" in error_text:
        print("Hint: copy .env.example to .env and set DB_PASSWORD.")
    elif "host.docker.internal" in error_text:
        print("Hint: if you are running locally, set DB_HOST=localhost in .env.")
    elif "Connection timed out" in error_text or "could not connect to server" in error_text.lower():
        print("Hint: check that PostgreSQL is running and accepting connections on the configured host and port.")