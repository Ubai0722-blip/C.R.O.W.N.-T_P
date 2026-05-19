import sys
sys.path.insert(0, '.')
try:
    from src.memory.database import Database
    db = Database()
    print('DB path:', db.current_db_path)
    print('Persona:', db._current_persona)
    with db.get_conn() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print('Tables:', [t[0] for t in tables])
    print('Database OK')
except Exception as e:
    print(f'Database ERROR: {e}')
    import traceback
    traceback.print_exc()
