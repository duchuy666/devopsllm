#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
kubectl --context="$PROFILE" -n "$SOCK_SHOP_NAMESPACE" exec deployment/front-end -- node -e '
var http=require("http"), targets=["carts","orders","shipping","payment","user","catalogue"];
var pending=targets.length, failed=false;
targets.forEach(function(name) {
  var finished=false;
  function done(status,error) {
    if(finished) return; finished=true;
    console.log(JSON.stringify({service:name,status:status,error:error||null}));
    if(status!==200) failed=true;
    if(--pending===0) process.exit(failed?1:0);
  }
  var req=http.get("http://"+name+"/health",function(res){res.resume();done(res.statusCode);});
  req.setTimeout(5000,function(){req.abort();done(0,"timeout");});
  req.on("error",function(err){done(0,err.code);});
});'
