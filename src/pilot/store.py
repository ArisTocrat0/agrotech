"""Dedicated MariaDB journal; all user values are bound parameters."""
import json
import threading
import re
from pathlib import Path

class Store:
    def __init__(self, config):
        import pymysql
        self.lock = threading.RLock()
        settings=json.loads(Path(config).read_text())
        self.table=settings.pop('_table','photos')
        if not re.fullmatch(r'photos(?:_tests)?',self.table):raise ValueError('Invalid internal table name')
        self.db = pymysql.connect(**settings, autocommit=True,
                                  charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        self.execute('''CREATE TABLE IF NOT EXISTS photos (
            id CHAR(32) PRIMARY KEY, mission VARCHAR(80) NOT NULL, sha256 CHAR(64) NOT NULL,
            state VARCHAR(20) NOT NULL, created VARCHAR(40) NOT NULL, body LONGTEXT NOT NULL,
            UNIQUE KEY mission_sha (mission, sha256)) ENGINE=InnoDB''')
        for row in self.list():
            if row['state'] == 'running':
                self.update(row['id'], state='error', error='Сервер остановлен во время анализа. Повторите обработку.')

    def execute(self, sql, args=()):
        with self.lock, self.db.cursor() as cursor:
            self.db.ping(reconnect=True)
            cursor.execute(sql.replace('photos',self.table), args)
            return cursor.fetchall()

    def list(self):
        return [json.loads(r['body']) for r in self.execute('SELECT body FROM photos ORDER BY created,id')]

    def get(self, key):
        rows=self.execute('SELECT body FROM photos WHERE id=%s', (key,))
        if not rows: raise ValueError('Снимок не найден.')
        return json.loads(rows[0]['body'])

    def duplicate(self, mission, digest):
        rows=self.execute('SELECT body FROM photos WHERE mission=%s AND sha256=%s', (mission,digest))
        return json.loads(rows[0]['body']) if rows else None

    def add(self, row):
        self.execute('INSERT INTO photos (id,mission,sha256,state,created,body) VALUES (%s,%s,%s,%s,%s,%s)',
                     (row['id'],row.get('dedup_mission',row['mission']),row['sha256'],row['state'],row['created'],json.dumps(row,ensure_ascii=False,allow_nan=False)))

    def update(self, key, **fields):
        with self.lock:
            row=self.get(key); row.update(fields)
            self.execute('UPDATE photos SET state=%s,body=%s WHERE id=%s',
                         (row['state'],json.dumps(row,ensure_ascii=False,allow_nan=False),key))
            return row
