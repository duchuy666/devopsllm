"""MySQL testbed helpers; credentials stay inside the target container."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE

SOURCE='deployment/catalogue-db'
EXPECTED={'performance_schema':'OFF','innodb_buffer_pool_size':'67108864',
    'innodb_buffer_pool_chunk_size':'67108864','innodb_buffer_pool_instances':'1',
    'max_connections':'30','table_open_cache':'128','table_definition_cache':'400',
    'tmp_table_size':'8388608','max_heap_table_size':'8388608','query_cache_size':'0'}


def execute(resource,tool,args=(),input_data=None,timeout=150):
    command='MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec timeout 120s '+tool+' -uroot "$@"'
    return subprocess.run(KUBE+['-n','sock-shop','exec']+(['-i'] if input_data is not None else [])+
        [resource,'--','sh','-c',command,'sh']+list(args),input=input_data,capture_output=True,check=True,timeout=timeout)


def sql(resource,query):
    return execute(resource,'mysql',['--batch','--skip-column-names','-e',query]).stdout.decode().strip()


def variables(resource):
    keys=','.join("'"+k+"'" for k in EXPECTED)
    return dict(row.split('\t',1) for row in sql(resource,'SHOW GLOBAL VARIABLES WHERE Variable_name IN ('+keys+');').splitlines())


def inventory(resource):
    names=sql(resource,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='socksdb' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME;").splitlines()
    if not names:raise RuntimeError('No catalogue business tables')
    tables=[]
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9_]+',name):raise ValueError('Unexpected SQL identifier')
        table='socksdb.`'+name+'`'
        checksum=sql(resource,'CHECKSUM TABLE '+table+' EXTENDED;').split('\t')[-1]
        if checksum=='NULL':raise RuntimeError('Table checksum unavailable')
        tables.append({'table':name,'rows':int(sql(resource,'SELECT COUNT(*) FROM '+table+';')),
            'checksum':checksum,'schema_sha256':hashlib.sha256(sql(resource,'SHOW CREATE TABLE '+table+';').encode()).hexdigest()})
    accounts=sql(resource,'SELECT User,Host,plugin,authentication_string FROM mysql.user ORDER BY User,Host;')
    return {'tables':tables,'account_auth_sha256':hashlib.sha256(accounts.encode()).hexdigest()}


def backup(path,resource=SOURCE):
    path=Path(path)
    command='MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec timeout 120s mysqldump -uroot --databases mysql socksdb --single-transaction --routines --events --triggers --hex-blob --flush-privileges --set-gtid-purged=OFF'
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
        subprocess.run(KUBE+['-n','sock-shop','exec',resource,'--','sh','-c',command],stdout=out,stderr=subprocess.PIPE,check=True,timeout=150)
    if path.stat().st_size<1024:raise RuntimeError('Backup unexpectedly small')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(path,resource):
    return execute(resource,'mysql',input_data=Path(path).read_bytes())
