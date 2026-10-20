from http.server import BaseHTTPRequestHandler,HTTPServer
import json,re,os,time,threading
MAX_BODY_BYTES=16000
POST_LIMIT=20
POST_WINDOW_SECONDS=60
_post_lock=threading.Lock()
_post_window_start=time.monotonic()
_post_count=0
MAX_DIAGNOSIS_CHARS=8000
VALID_SYSTEMS={'http','api','mcp'}
R=re.compile(r'''(?isx)
    (?:
      -----BEGIN [^-]*KEY-----.*?-----END [^-]*KEY-----
      |\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@
      |\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}
      |\b(?:sk[-_](?:live|test|proj|ant)[-_]?[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,})
      |\b(?:AKIA|ASIA)[A-Z0-9]{16}\b
      |\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b
      |\b(?:aws_secret_access_key|secret_access_key|client_secret|password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*['\"]?[^\s,;'\"]+
      |[\w.+-]+@[\w.-]+\.[a-z]{2,}
    )''')
RULES=[('429','rate_limit','Honor Retry-After; reduce concurrency and use bounded jittered backoff.','low'),('401','authentication','Check credential expiry, audience and scope; rotate exposed secrets.','high'),('403','authorization','Review permissions; do not broaden access automatically.','high'),('timeout','timeout','Check upstream latency and use bounded retries for idempotent requests.','medium'),('503','unavailable','Check dependency health and use a circuit breaker.','medium'),('502','gateway','Check upstream reachability, DNS and TLS.','medium'),('certificate','tls','Verify hostname and certificate chain; never disable TLS checks.','high'),('connection refused','connectivity','Confirm service host, port and listener.','medium'),('500','server_error','Inspect upstream logs by request ID; retry only idempotent requests.','medium'),('protocol version','mcp_protocol','Compare client and server protocol versions; confirm initialize negotiation and required capabilities.','medium'),('invalid json','mcp_protocol','Validate the MCP JSON-RPC envelope, content type, request ID and result shape.','medium'),('oauth token expired','authentication','Refresh OAuth through the configured flow; never expose or log tokens.','high'),('dns','dns','Check hostname, resolver health and service discovery.','medium'),('reset by peer','connectivity','Check upstream restarts and proxy or idle-connection timeouts.','medium'),('required','bad_request','Validate the request schema and required fields against the API version.','low'),('404','not_found','Check endpoint path, API version, resource identifier and environment.','low'),('no result','semantic_failure','Transport success can hide task failure. Inspect expected output and tool result content before retrying.','medium')]
def diagnose(error,system='http'):
 s=R.sub('[REDACTED]',str(error)[:MAX_DIAGNOSIS_CHARS]);lo=s.lower();q=next((r for r in RULES if r[0] in lo),None)
 if q: sig,cat,advice,risk=q;confidence='medium';basis='A deterministic rule matched a known error phrase; this is not a calibrated probability.'
 else: sig,cat,advice,risk,confidence,basis='','unknown','Capture a sanitized trace, timestamp and request ID; compare with a known-good run.','medium','low','No known error phrase matched; gather more evidence before acting.'
 return {'system':system,'category':cat,'summary':s[:500],'confidence':confidence,'confidence_basis':basis,'recovery':{'guidance':advice,'risk':risk,'requires_human_approval':risk=='high','execute_automatically':False},'evidence':{'signals':[sig] if sig else [],'redacted':'[REDACTED]' in s},'payment':{'mode':'test','charged':False}}
SCHEMA={
 'openapi':'3.1.0','info':{'title':'AgentRescue API','version':'0.1.0','description':'Rule-based, advisory HTTP/API/MCP failure diagnosis. Fixes are never executed.'},
 'paths':{
  '/v1/diagnose':{'post':{'operationId':'diagnoseFailure','summary':'Diagnose a sanitized failure','requestBody':{'required':True,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/DiagnoseRequest'}}}},'responses':{'200':{'description':'Diagnosis with gated recovery guidance','content':{'application/json':{'schema':{'$ref':'#/components/schemas/Diagnosis'}}}},'400':{'description':'Invalid JSON, system, or missing error text'},'411':{'description':'Content-Length header required'},'413':{'description':'Body exceeds 16 KB or diagnostic text exceeds 8,000 characters'}}}},
 },
 'components':{'schemas':{
  'DiagnoseRequest':{'type':'object','properties':{'error':{'type':'string','minLength':1,'maxLength':8000},'system':{'type':'string','enum':['http','api','mcp'],'default':'http'}},'required':['error'],'additionalProperties':False},
  'Diagnosis':{'type':'object','properties':{'system':{'type':'string'},'category':{'type':'string'},'summary':{'type':'string'},'confidence':{'type':'string','enum':['low','medium','high']},'confidence_basis':{'type':'string'},'recovery':{'type':'object','properties':{'guidance':{'type':'string'},'risk':{'type':'string','enum':['low','medium','high']},'requires_human_approval':{'type':'boolean'},'execute_automatically':{'type':'boolean'}},'required':['guidance','risk','requires_human_approval','execute_automatically']},'evidence':{'type':'object','properties':{'signals':{'type':'array','items':{'type':'string'}},'redacted':{'type':'boolean'}},'required':['signals','redacted']},'payment':{'type':'object','properties':{'mode':{'type':'string','const':'test'},'charged':{'type':'boolean','const':False}},'required':['mode','charged']}},'required':['system','category','summary','confidence','confidence_basis','recovery','evidence','payment']},
 }}
}
LLMS='''# AgentRescue

> MCP diagnostic tool for LLM agents facing HTTP, API, and MCP failures.

## Connect
- MCP endpoint: POST /mcp (protocol 2026-07-28 stateless and legacy 2025 initialize).
- MCP tool: diagnose_failure.
- HTTP API: POST /v1/diagnose.
- OpenAPI: /openapi.json.

## Safety and payment
- Send sanitized diagnostic text only; never include credentials or personal data.
- Advice is informational and never runs a fix. High-risk advice requires human review.
- Evaluation is free and no-charge; payment support is not enabled. Requests are processed in memory and are not logged or stored. A service-wide POST limit applies.
'''
ROBOTS='''User-agent: *
Allow: /
Disallow: /v1/feedback
'''
HTML='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AgentRescue | Safer agent recovery</title><meta name="description" content="Diagnose HTTP, API and MCP failures with structured recovery guidance."><style>body{font:18px system-ui;max-width:760px;margin:10vh auto;padding:0 24px;background:#101a21;color:#e8f1ee}h1{font-size:3rem}p{line-height:1.6;color:#bbcbc7}textarea{width:100%;height:90px}button{padding:12px;background:#a6efc2;border:0}pre{white-space:pre-wrap;background:#192830;padding:16px}</style><small>AGENTRESCUE · TEST MODE</small><h1>Safer next steps for failing agents.</h1><p>Paste an HTTP, API or MCP error for structured diagnosis, evidence, confidence and recovery advice. High-risk steps require review. Fixes never run automatically.</p><textarea id="e">HTTP 429 rate limit</textarea><p><button id="go">Diagnose · no charge</button></p><pre id="o">Result appears here.</pre><p>API: POST /v1/diagnose · MCP: /mcp · <a href="/openapi.json">OpenAPI</a>. Test mode only; no payment is collected.</p><script>go.onclick=async()=>{let r=await fetch('/v1/diagnose',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({error:e.value})});o.textContent=JSON.stringify(await r.json(),null,2)}</script></html>'''
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,status,obj,typ='application/json'):
  b=obj if isinstance(obj,bytes) else json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(b)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/llms.txt':return self.send(200,LLMS.encode(),'text/plain; charset=utf-8')
  if self.path=='/robots.txt':return self.send(200,ROBOTS.encode(),'text/plain; charset=utf-8')
  if self.path=='/openapi.json':return self.send(200,SCHEMA)
  if self.path=='/health':return self.send(200,{'status':'ok'})
  if self.path=='/':return self.send(200,HTML.encode(),'text/html; charset=utf-8')
  self.send(404,{'error':'not_found'})
 def do_POST(self):
  global _post_window_start,_post_count
  now=time.monotonic()
  with _post_lock:
   if now-_post_window_start>=POST_WINDOW_SECONDS:_post_window_start=now;_post_count=0
   if _post_count>=POST_LIMIT:return self.send(429,{'error':'rate_limit','retry_after_seconds':max(1,int(POST_WINDOW_SECONDS-(now-_post_window_start)))})
   _post_count+=1
  raw_length=self.headers.get('Content-Length')
  if raw_length is None:return self.send(411,{'error':'content_length_required'})
  if not raw_length.isdecimal():return self.send(400,{'error':'invalid_content_length'})
  if len(raw_length)>20:return self.send(413,{'error':'payload_too_large'})
  n=int(raw_length)
  if n>MAX_BODY_BYTES:return self.send(413,{'error':'payload_too_large'})
  if n==0:return self.send(400,{'error':'invalid_json'})
  body=self.rfile.read(n)
  if len(body)!=n:return self.send(400,{'error':'incomplete_body'})
  try:d=json.loads(body)
  except:return self.send(400,{'error':'invalid_json'})
  if not isinstance(d,dict):return self.send(400,{'error':'json_object_required'})
  if self.path=='/v1/diagnose':
   if not isinstance(d.get('error'),str) or not d['error'].strip():return self.send(400,{'error':'error_required'})
   if len(d['error'])>MAX_DIAGNOSIS_CHARS:return self.send(413,{'error':'diagnostic_too_large','max_chars':MAX_DIAGNOSIS_CHARS})
   system=d.get('system','http')
   if not isinstance(system,str) or system not in VALID_SYSTEMS:return self.send(400,{'error':'invalid_system','allowed':sorted(VALID_SYSTEMS)})
   return self.send(200,diagnose(d['error'],system))
  if self.path=='/v1/feedback':return self.send(404,{'error':'not_found'})
  if self.path=='/mcp':
   origin=self.headers.get('Origin')
   if origin and origin not in ('http://'+self.headers.get('Host',''), 'https://'+self.headers.get('Host','')): return self.send(403,{'error':'origin_not_allowed'})
   return self.mcp(d)
  self.send(404,{'error':'not_found'})
 def mcp(self,d):
  method=d.get('method');ident=d.get('id');params=d.get('params') or {}
  def result(value,status=200): self.send(status,{'jsonrpc':'2.0','id':ident,'result':value})
  def error(code,message,status=200,data=None):
   body={'jsonrpc':'2.0','id':ident,'error':{'code':code,'message':message}}
   if data is not None: body['error']['data']=data
   self.send(status,body)
  if not isinstance(method,str) or not method:return error(-32600,'Invalid Request')
  if params is None:params={}
  if not isinstance(params,dict):return error(-32602,'params must be an object')
  meta=params.get('_meta',{})
  if meta is None:meta={}
  if not isinstance(meta,dict):return error(-32602,'_meta must be an object')
  version=meta.get('io.modelcontextprotocol/protocolVersion')
  modern=version is not None
  # This service deliberately supports current stateless HTTP plus legacy handshake clients.
  modern_versions=['2026-07-28']; legacy_versions=['2025-11-25','2025-06-18','2025-03-26']
  if modern:
   if version not in modern_versions:
    return error(-32022,'Unsupported protocol version',400,{'supported':modern_versions,'requested':version})
   if self.headers.get('MCP-Protocol-Version') != version or self.headers.get('Mcp-Method') != method:
    return error(-32020,'Header mismatch',400)
   if method=='tools/call' and self.headers.get('Mcp-Name') != params.get('name'):
    return error(-32020,'Header mismatch',400)
   if method=='server/discover':
    return result({'resultType':'complete','supportedVersions':modern_versions,'capabilities':{'tools':{}},'_meta':{'io.modelcontextprotocol/serverInfo':{'name':'agentrescue','version':'0.1.0'}},'instructions':'Use diagnose_failure with a sanitized HTTP, API, or MCP error. Recommendations are advisory; high-risk actions require human review.','ttlMs':300000,'cacheScope':'public'})
  elif method=='initialize':
   req=(params.get('protocolVersion') or '2025-03-26')
   chosen=req if req in legacy_versions else '2025-11-25'
   return result({'protocolVersion':chosen,'capabilities':{'tools':{}},'serverInfo':{'name':'agentrescue','version':'0.1.0'}})
  elif method=='server/discover':
   # Discovery must be called using modern metadata; legacy clients receive a clear error.
   return error(-32602,'server/discover requires protocol version metadata')
  if method=='notifications/initialized' or (ident is None and method.startswith('notifications/')):
   self.send(202,b'');return
  if method=='ping': return result({})
  if method=='tools/list':
   return result({'resultType':'complete','tools':[{'name':'diagnose_failure','title':'Diagnose agent tool failure','description':'Diagnose a sanitized HTTP/API/MCP error and return safe, structured recovery guidance. Never executes remediation.','inputSchema':{'type':'object','properties':{'error':{'type':'string','minLength':1,'maxLength':MAX_DIAGNOSIS_CHARS},'system':{'type':'string','enum':['http','api','mcp']}},'required':['error'],'additionalProperties':False},'outputSchema':{'type':'object','properties':{'system':{'type':'string'},'category':{'type':'string'},'summary':{'type':'string'},'confidence':{'type':'string','enum':['low','medium','high']},'confidence_basis':{'type':'string'},'recovery':{'type':'object'},'evidence':{'type':'object'},'payment':{'type':'object'}},'required':['system','category','summary','confidence','confidence_basis','recovery','evidence','payment']},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}],'ttlMs':300000,'cacheScope':'public'})
  if method=='tools/call':
   args=params.get('arguments',{})
   if args is None:args={}
   if not isinstance(args,dict):return error(-32602,'arguments must be an object')
   err=args.get('error')
   if not isinstance(err,str) or not err.strip():return error(-32602,'error argument is required')
   if len(err)>MAX_DIAGNOSIS_CHARS:return error(-32602,'error exceeds maximum length',data={'maxChars':MAX_DIAGNOSIS_CHARS})
   system=args.get('system','mcp')
   if not isinstance(system,str) or system not in VALID_SYSTEMS:return error(-32602,'invalid system',data={'allowed':sorted(VALID_SYSTEMS)})
   diagnosis=diagnose(err,system)
   return result({'resultType':'complete','content':[{'type':'text','text':json.dumps(diagnosis)}],'structuredContent':diagnosis,'isError':False})
  return error(-32601,'Method not found',404 if modern else 200)
if __name__=='__main__':HTTPServer((os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','8000'))),H).serve_forever()
