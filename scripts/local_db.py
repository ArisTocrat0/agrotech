"""Start a project-owned MariaDB via private Unix socket, never system DB."""
import argparse,json,os,secrets,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/pilot-db'

def main():
    import pymysql
    p=argparse.ArgumentParser();p.add_argument('--stop',action='store_true');args=p.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);BASE.chmod(0o700)
    sock=str(BASE/'mysql.sock'); conf=BASE/'client.json'; pidfile=BASE/'server.pid'
    if args.stop:
        if not conf.exists(): return
        cfg=json.loads(conf.read_text())
        # Admin credentials are private and separate from the application user.
        admin=json.loads((BASE/'admin.json').read_text())
        with pymysql.connect(**admin) as db:
            with db.cursor() as c: c.execute('SHUTDOWN')
        print('Локальная MariaDB Экокинеу остановлена.');return
    try:
        if conf.exists():
            with pymysql.connect(**json.loads(conf.read_text())) as db: db.ping()
            print('MariaDB Экокинеу уже доступна.');return
    except pymysql.Error: pass
    if not (BASE/'data/mysql').exists():
        subprocess.run(['mariadb-install-db','--no-defaults','--datadir='+str(BASE/'data'),
                        '--auth-root-authentication-method=normal','--skip-test-db'],check=True,stdout=subprocess.DEVNULL)
    log=(BASE/'server.log').open('ab')
    subprocess.Popen(['mariadbd','--no-defaults','--datadir='+str(BASE/'data'),'--socket='+sock,
                      '--pid-file='+str(pidfile),'--skip-networking','--innodb-buffer-pool-size=64M',
                      '--max-connections=12','--log-error='+str(BASE/'error.log')],stdout=log,stderr=log,start_new_session=True)
    adminpath=BASE/'admin.json'
    admin=json.loads(adminpath.read_text()) if adminpath.exists() else {'user':'root','unix_socket':sock}
    for _ in range(100):
        try: db=pymysql.connect(**admin);break
        except pymysql.Error: time.sleep(.1)
    else: raise RuntimeError('MariaDB не запустилась; см. outputs/pilot-db/error.log')
    if not conf.exists():
        password=secrets.token_urlsafe(36); rootpass=secrets.token_urlsafe(36)
        with db.cursor() as c:
            c.execute('CREATE DATABASE IF NOT EXISTS ecokineu_pilot CHARACTER SET utf8mb4')
            c.execute("CREATE USER IF NOT EXISTS 'ecokineu'@'localhost' IDENTIFIED BY %s",(password,))
            c.execute("GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,INDEX ON ecokineu_pilot.* TO 'ecokineu'@'localhost'")
            c.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",(rootpass,))
        for path,data in [(conf,{'user':'ecokineu','password':password,'unix_socket':sock,'database':'ecokineu_pilot'}),
                          (adminpath,{'user':'root','password':rootpass,'unix_socket':sock})]:
            path.write_text(json.dumps(data));path.chmod(0o600)
    db.close(); print('MariaDB Экокинеу: отдельная база, Unix socket, TCP отключён.')
if __name__=='__main__': main()
