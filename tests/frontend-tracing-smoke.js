'use strict';
var http = require('http');
var url = require('url');
var assert = require('assert');
var childProcess = require('child_process');
var path = require('path');

if (process.argv[2] === '--child') {
  var tracer=require(process.env.SHYN_TRACER_PATH || path.resolve(__dirname,'../infra/tracing/frontend-tracing.js'));
  assert.strictEqual(tracer.safePeer('user:80'),'user');
  assert.strictEqual(tracer.safePeer('carts.sock-shop.svc.cluster.local'),'carts');
  assert.strictEqual(tracer.safePeer('user.private.example.com'),null);
  assert.strictEqual(tracer.safePath('/customers/alice@example.com?password=secret'),'/customers/:id');
  assert.strictEqual(tracer.safePath('/alice@example.com'),'/:route');
  var server = http.createServer(function(request,response) {
    var target = url.parse(process.env.SHYN_TEST_DOWNSTREAM+request.url);
    target.headers = {Authorization:'Bearer DO_NOT_EXPORT_DOWNSTREAM'};
    http.get(target,function(upstream) {
      var body = '';
      upstream.on('data',function(chunk) { body += chunk; });
      upstream.on('end',function() { response.statusCode=upstream.statusCode; response.end(body); });
    }).on('error',function() { response.statusCode=502;response.end('upstream-error'); });
  });
  server.listen(0,'127.0.0.1',function() { process.send({port:server.address().port}); });
} else {
  var spans = [];
  var received = {};
  var child;
  var childErrors = '';
  var done = false;
  var watchdog = setTimeout(function() { finish(new Error('Trace smoke timed out')); },12000);
  var downstream = http.createServer(function(request,response) {
    var route = url.parse(request.url).pathname;
    received[route] = request.headers;
    setTimeout(function() { response.statusCode=route === '/error' ? 503 : 200;response.end('backend-ok'); },route === '/slow' ? 30 : 2);
  });
  var collector = http.createServer(function(request,response) {
    var body = '';
    request.on('data',function(chunk) { body += chunk; });
    request.on('end',function() {
      try { spans = spans.concat(JSON.parse(body));response.statusCode=202;response.end(); }
      catch (error) { response.statusCode=400;response.end();finish(error); }
    });
  });
  function finish(error) {
    if (done) return;done=true;clearTimeout(watchdog);
    if (child) child.kill('SIGTERM');
    downstream.close();collector.close();
    if (error) { console.error(error.stack);if(childErrors)console.error(childErrors);process.exitCode=1; }
    else console.log(JSON.stringify({status:'passed',node:process.version,exported_spans:spans.length,
      checks:['concurrent_context_isolation','b3_parent_propagation','sampling_deny','http_status_preserved','no_headers_query_body_or_object_id_export']}));
  }
  downstream.listen(0,'127.0.0.1',function() {
    collector.listen(0,'127.0.0.1',function() {
      var env = {};
      Object.keys(process.env).forEach(function(key) { env[key] = process.env[key]; });
      env.SHYN_ZIPKIN_URL='http://127.0.0.1:'+collector.address().port+'/api/v1/spans';
      env.SHYN_TEST_DOWNSTREAM='http://127.0.0.1:'+downstream.address().port;
      env.SHYN_TRACE_FLUSH_MS='100';
      var tracer = process.env.SHYN_TRACER_PATH || path.resolve(__dirname,'../infra/tracing/frontend-tracing.js');
      child=childProcess.spawn(process.execPath,['--require',tracer,__filename,'--child'],{env:env,stdio:['ignore','pipe','pipe','ipc']});
      child.stderr.on('data',function(data) { childErrors += data.toString(); });
      child.on('error',finish);
      child.on('exit',function(code,signal) { if (!done) finish(new Error('Child exited: '+code+' '+signal)); });
      child.on('message',function(message) { runRequests(message.port); });
    });
  });
  function runRequests(port) {
    var tasks=[
      {route:'/fast',trace:'1111111111111111',parent:'aaaaaaaaaaaaaaaa'},
      {route:'/slow',trace:'2222222222222222',parent:'bbbbbbbbbbbbbbbb'},
      {route:'/customers/0123456789abcdef01234567?token=DO_NOT_EXPORT_QUERY',trace:'3333333333333333',parent:'cccccccccccccccc'},
      {route:'/error',trace:'4444444444444444',parent:'dddddddddddddddd'},
      {route:'/disabled',trace:'5555555555555555',parent:'eeeeeeeeeeeeeeee',sampled:'0'}];
    var remaining=tasks.length;
    tasks.forEach(function(task) {
      var request=http.get({hostname:'127.0.0.1',port:port,path:task.route,
        headers:{'X-B3-TraceId':task.trace,'X-B3-SpanId':task.parent,'X-B3-Sampled':task.sampled || '1',Authorization:'Bearer DO_NOT_EXPORT_INCOMING'}},function(response) {
          var body='';response.on('data',function(chunk) {body+=chunk;});
          response.on('end',function() {
            try {assert.strictEqual(response.statusCode,task.route === '/error' ? 503 : 200);assert.strictEqual(body,'backend-ok');}
            catch(error) {finish(error);return;}
            if (--remaining===0) verify(tasks,Date.now()+4000);
          });
        });
      request.on('error',finish);
    });
  }
  function verify(tasks,deadline) {
    if (done) return;
    if (spans.length<8 && Date.now()<deadline) {setTimeout(function() {verify(tasks,deadline);},50);return;}
    try {
      assert.strictEqual(spans.length,8);
      assert.strictEqual(JSON.stringify(spans).indexOf('DO_NOT_EXPORT'),-1);
      assert.strictEqual(JSON.stringify(spans).indexOf('0123456789abcdef01234567'),-1);
      tasks.forEach(function(task) {
        var route=url.parse(task.route).pathname;
        assert.strictEqual(received[route]['x-b3-traceid'],task.trace);
        assert.strictEqual(received[route]['x-b3-sampled'],task.sampled || '1');
        var matching=spans.filter(function(span) {return span.traceId===task.trace;});
        if(task.sampled==='0') {assert.strictEqual(matching.length,0);return;}
        assert.strictEqual(matching.length,2);
        var server=matching.filter(function(span) {return span.annotations[0].value==='sr';})[0];
        var client=matching.filter(function(span) {return span.annotations[0].value==='cs';})[0];
        assert.strictEqual(server.parentId,task.parent);
        assert.strictEqual(client.parentId,server.id);
        assert.strictEqual(received[route]['x-b3-spanid'],client.id);
        assert.strictEqual(received[route]['x-b3-parentspanid'],server.id);
      });
      finish();
    } catch(error) {finish(error);}
  }
}
