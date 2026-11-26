#!/bin/sh
# A bounded postStart hook. Do not change mongod's startup or seed-data command.
set -eu
command -v timeout >/dev/null 2>&1 || { echo 'SHYN cache hook requires timeout' >&2; exit 78; }
command -v mongo >/dev/null 2>&1 || { echo 'SHYN cache hook requires mongo' >&2; exit 78; }
attempt=0
while [ "$attempt" -lt 30 ]; do
    attempt=$((attempt + 1))
    if timeout 5s mongo --quiet --host 127.0.0.1 --eval '
        var r=db.adminCommand({setParameter:1,wiredTigerEngineRuntimeConfig:"cache_size=128M"});
        if (r.ok !== 1) quit(2);
        var size=db.serverStatus().wiredTiger.cache["maximum bytes configured"];
        if (size !== 134217728) quit(3);
        print("SHYN_DB_CACHE_READY bytes="+size);
    '; then
        exit 0
    fi
    sleep 1
done
echo 'SHYN cache hook did not obtain verified 128MiB within bounded attempts' >&2
exit 1
