/* ES5-compatible, dependency-free Zipkin v1/B3 instrumentation for Sock Shop.
 * Export HTTP metadata only. Never export headers, query strings or bodies.
 */
'use strict';
var http = require('http');
var url = require('url');
var crypto = require('crypto');
var domain = require('domain');
var originalRequest = http.request;
var originalGet = http.get;
var originalServerEmit = http.Server.prototype.emit;
var collector = url.parse(process.env.SHYN_ZIPKIN_URL || 'http://jaeger.monitoring.svc.cluster.local:9411/api/v1/spans');
if (collector.protocol !== 'http:' || !collector.hostname || collector.auth) throw new Error('Invalid local tracing endpoint');
var endpoint = {serviceName: 'front-end'};
var queue = [];
var dropped = 0;
var inflight = false;

function id() { return crypto.randomBytes(8).toString('hex'); }
function valid(value, trace) {
  return typeof value === 'string' && (trace ? /^(?:[a-f0-9]{16}|[a-f0-9]{32})$/ : /^[a-f0-9]{16}$/).test(value) && !/^0+$/.test(value);
}
function safePath(value) {
  var path = url.parse(String(value || '/')).pathname || '/';
  var segments = path.split('/').filter(function(part) {return part.length>0;});
  if (!segments.length) return '/';
  var routes = ['catalogue','cart','orders','login','register','cards','addresses','customers','tags','health','metrics'];
  if (routes.indexOf(segments[0])<0) return '/:route';
  return '/'+segments.map(function(part,index) {
    if (index===0) return part;
    return index===2 && ['cards','addresses','items'].indexOf(part)>=0 ? part : ':id';
  }).join('/').slice(0,150);
}
function safePeer(value) {
  var peer = String(value || '').toLowerCase().replace(/:\d+$/,'');
  var parts = peer.split('.');
  if (parts.length>1 && ['sock-shop','sock-shop.svc','sock-shop.svc.cluster.local'].indexOf(parts.slice(1).join('.'))<0) return null;
  var allowed = ['front-end','catalogue','user','carts','orders','payment','shipping','user-db','carts-db','orders-db','catalogue-db','rabbitmq','session-db','queue-master'];
  return allowed.indexOf(parts[0])>=0 ? parts[0] : null;
}
function copy(object) {
  var result = {};
  Object.keys(object || {}).forEach(function(key) { result[key] = object[key]; });
  return result;
}
function incoming(headers) {
  var trace = headers['x-b3-traceid'];
  var parent = headers['x-b3-spanid'];
  var sampled = headers['x-b3-sampled'] !== '0' && headers['x-b3-sampled'] !== 'false';
  var debug = headers['x-b3-flags'] === '1';
  var single = headers.b3;
  if (single === '0') sampled = false;
  else if (single === '1' || single === 'd') { sampled = true; debug = single === 'd'; }
  else if (typeof single === 'string') {
    var fields = single.split('-');
    if (valid(fields[0],true) && valid(fields[1],false)) {
      trace = fields[0]; parent = fields[1]; sampled = fields[2] !== '0'; debug = fields[2] === 'd';
    }
  }
  if (!valid(trace,true) || !valid(parent,false)) { trace = id(); parent = null; }
  return {traceId:trace,spanId:id(),parentId:parent,sampled:debug || sampled,debug:debug};
}
function timer() { return {timestamp:Date.now()*1000,monotonic:process.hrtime()}; }
function record(context,clock,name,kind,status,error,remote) {
  if (!context.sampled) return;
  var elapsed = process.hrtime(clock.monotonic);
  var duration = Math.max(1,Math.round(elapsed[0]*1000000+elapsed[1]/1000));
  var span = {traceId:context.traceId,id:context.spanId,name:name,timestamp:clock.timestamp,duration:duration,
    annotations:[{timestamp:clock.timestamp,value:kind === 'server' ? 'sr' : 'cs',endpoint:endpoint},
                 {timestamp:clock.timestamp+duration,value:kind === 'server' ? 'ss' : 'cr',endpoint:endpoint}],
    binaryAnnotations:[{key:'http.status_code',value:String(status || 0),endpoint:endpoint}]};
  if (context.parentId) span.parentId = context.parentId;
  if (error || status >= 500) span.binaryAnnotations.push({key:'error',value:true,endpoint:endpoint});
  var peer=safePeer(remote);
  if (peer) span.binaryAnnotations.push({key:'peer.service',value:peer,endpoint:endpoint});
  if (queue.length < 1000) queue.push(span); else dropped++;
}
function flush() {
  if (inflight || !queue.length) return;
  var batch = queue.splice(0,128);
  var data = JSON.stringify(batch);
  inflight = true;
  var request = originalRequest.call(http,{hostname:collector.hostname,port:collector.port || 80,
    path:collector.path,method:'POST',headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(data)}},function(response) {
      response.resume();
      response.on('end',function() { if (response.statusCode < 200 || response.statusCode >= 300) dropped += batch.length; inflight = false; });
      response.on('error',function() { dropped += batch.length; inflight = false; });
    });
  request.setTimeout(3000,function() { request.destroy(); });
  request.on('error',function() { dropped += batch.length; inflight = false; });
  request.end(data);
}

http.Server.prototype.emit = function(event,request,response) {
  if (event !== 'request') return originalServerEmit.apply(this,arguments);
  var server = this;
  var context = incoming(request.headers);
  var clock = timer();
  var active = domain.create();
  active.shynTrace = context;
  var result;
  active.run(function() {
    var finished = false;
    function finish(error) {
      if (finished) return; finished = true;
      record(context,clock,String(request.method || 'GET')+' '+safePath(request.url),'server',response.statusCode,error);
    }
    response.once('finish',function() { finish(false); });
    response.once('close',function() { finish(true); });
    result = originalServerEmit.call(server,event,request,response);
  });
  return result;
};

http.request = function(input) {
  var parent = domain.active && domain.active.shynTrace;
  if (!parent) return originalRequest.apply(http,arguments);
  var args = arguments;
  var options = typeof input === 'string' ? url.parse(input) : copy(input);
  if (typeof args[1] === 'object') {
    Object.keys(args[1]).forEach(function(key) { options[key] = args[1][key]; });
  }
  if (Array.isArray(options.headers)) return originalRequest.apply(http,args);
  options.headers = copy(options.headers);
  Object.keys(options.headers).forEach(function(key) { if (/^x-b3-/i.test(key) || key.toLowerCase() === 'b3') delete options.headers[key]; });
  var context = {traceId:parent.traceId,spanId:id(),parentId:parent.spanId,sampled:parent.sampled,debug:parent.debug};
  options.headers['x-b3-traceid'] = context.traceId;
  options.headers['x-b3-spanid'] = context.spanId;
  options.headers['x-b3-parentspanid'] = context.parentId;
  if (context.debug) options.headers['x-b3-flags'] = '1';
  else options.headers['x-b3-sampled'] = context.sampled ? '1' : '0';
  var callback = typeof args[args.length-1] === 'function' ? args[args.length-1] : undefined;
  var clock = timer();
  var finished = false;
  function finish(status,error) {
    if (finished) return; finished = true;
    record(context,clock,'http:'+safePath(options.path),'client',status,error,options.hostname || options.host);
  }
  var request = originalRequest.call(http,options,callback);
  request.once('response',function(response) {
    response.once('end',function() { finish(response.statusCode,false); });
    response.once('aborted',function() { finish(response.statusCode,true); });
  });
  // Preserve Node's original error handling, including an unhandled error throw.
  var emit = request.emit;
  request.emit = function(event) {
    if (event === 'error' || event === 'abort') finish(0,true);
    return emit.apply(this,arguments);
  };
  return request;
};
http.get = function() {
  if (!(domain.active && domain.active.shynTrace)) return originalGet.apply(http,arguments);
  var request = http.request.apply(http,arguments); request.end(); return request;
};
var interval = Number(process.env.SHYN_TRACE_FLUSH_MS || 1000);
if (!(interval >= 100 && interval <= 5000)) interval = 1000;
setInterval(flush,interval).unref();
var lastReportedDrop = 0;
setInterval(function() {
  if (dropped !== lastReportedDrop) {
    console.error('SHYN_TRACE_EXPORT_DROPPED total='+dropped);
    lastReportedDrop = dropped;
  }
},30000).unref();
module.exports = {safePath:safePath,safePeer:safePeer,flush:flush,diagnostics:function() { return {queued:queue.length,dropped:dropped}; }};
