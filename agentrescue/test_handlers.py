import io, json, unittest
from email.message import Message
from app import H
class Capture(H):
 def __init__(self, path, payload):
  self.path=path; self.headers=Message(); raw=json.dumps(payload).encode(); self.headers['Content-Length']=str(len(raw)); self.rfile=io.BytesIO(raw); self.response=None
 def send(self,status,obj,typ='application/json'): self.response=(status,obj)
class RawCapture(Capture):
 def __init__(self,path,body=b'{}',headers=None):
  self.path=path;self.headers=Message()
  for key,value in (headers or {}).items():self.headers[key]=value
  self.rfile=io.BytesIO(body);self.response=None
class HandlerTests(unittest.TestCase):
 def test_llms_txt_explains_agent_safety_and_payment(self):
  h=Capture('/llms.txt',{});h.do_GET()
  self.assertEqual(h.response[0],200);self.assertIn('LLM',h.response[1].decode());self.assertIn('no-charge',h.response[1].decode());self.assertIn('not logged or stored',h.response[1].decode())
 def test_tool_annotations_mark_read_only(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/list','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}});h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='tools/list';h.do_POST()
  ann=h.response[1]['result']['tools'][0]['annotations'];self.assertTrue(ann['readOnlyHint']);self.assertFalse(ann['destructiveHint'])
 def test_diagnosis_endpoint_response(self):
  h=Capture('/v1/diagnose',{'error':'MCP initialize invalid protocol version','system':'mcp'});h.do_POST()
  self.assertEqual(h.response[0],200); self.assertEqual(h.response[1]['category'],'mcp_protocol')
 def test_http_rejects_missing_and_invalid_lengths(self):
  missing=RawCapture('/v1/diagnose');missing.do_POST();self.assertEqual(missing.response[0],411)
  invalid=RawCapture('/v1/diagnose',headers={'Content-Length':'-1'});invalid.do_POST();self.assertEqual(invalid.response[0],400)
  huge=RawCapture('/v1/diagnose',headers={'Content-Length':'9'*5000});huge.do_POST();self.assertEqual(huge.response[0],413)
 def test_http_rejects_non_object_json_and_oversized_diagnostics(self):
  array=Capture('/v1/diagnose',[]);array.do_POST();self.assertEqual(array.response[0],400)
  long=Capture('/v1/diagnose',{'error':'x'*8001});long.do_POST();self.assertEqual(long.response[0],413)
 def test_http_rejects_unknown_system(self):
  h=Capture('/v1/diagnose',{'error':'HTTP 500','system':'shell'});h.do_POST()
  self.assertEqual(h.response[0],400);self.assertEqual(h.response[1]['error'],'invalid_system')
 def test_public_feedback_is_disabled(self):
  h=Capture('/v1/feedback',{'opt_in':True});h.do_POST()
  self.assertEqual(h.response[0],404);self.assertFalse(__import__('os').path.exists('data/feedback.jsonl'))
 def test_post_rate_limit_is_bounded(self):
  import app
  app._post_count=app.POST_LIMIT
  h=Capture('/v1/diagnose',{'error':'HTTP 429'});h.do_POST()
  self.assertEqual(h.response[0],429);self.assertGreaterEqual(h.response[1]['retry_after_seconds'],1)
  app._post_count=0
 def test_mcp_tools_call(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'diagnose_failure','arguments':{'error':'HTTP 429'}}});h.do_POST()
  self.assertEqual(h.response[0],200); self.assertEqual(h.response[1]['result']['structuredContent']['category'],'rate_limit')
 def test_mcp_rejects_bad_params_arguments_and_long_errors(self):
  params=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':[]});params.do_POST()
  self.assertEqual(params.response[1]['error']['code'],-32602)
  meta=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'_meta':[]}});meta.do_POST()
  self.assertEqual(meta.response[1]['error']['code'],-32602)
  args=Capture('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'arguments':[]}});args.do_POST()
  self.assertEqual(args.response[1]['error']['code'],-32602)
  long=Capture('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'arguments':{'error':'x'*8001}}});long.do_POST()
  self.assertEqual(long.response[1]['error']['code'],-32602)
 def test_mcp_null_params_is_valid_for_ping(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'ping','params':None});h.do_POST()
  self.assertEqual(h.response[1]['result'],{})
 def test_modern_server_discover(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'server/discover','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}});h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='server/discover';h.do_POST()
  self.assertEqual(h.response[0],200);self.assertEqual(h.response[1]['result']['supportedVersions'],['2026-07-28'])
 def test_modern_tools_list_has_cache_metadata(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/list','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}});h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='tools/list';h.do_POST()
  result=h.response[1]['result'];self.assertEqual(result['resultType'],'complete');self.assertEqual(result['cacheScope'],'public');self.assertEqual(result['tools'][0]['name'],'diagnose_failure')
 def test_modern_unsupported_version(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':4,'method':'server/discover','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2025-11-25'}}});h.headers['MCP-Protocol-Version']='2025-11-25';h.headers['Mcp-Method']='server/discover';h.do_POST()
  self.assertEqual(h.response[0],400);self.assertEqual(h.response[1]['error']['code'],-32022)
 def test_modern_header_mismatch_rejected(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/list','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}});h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='tools/call';h.do_POST()
  self.assertEqual(h.response[0],400);self.assertEqual(h.response[1]['error']['code'],-32020)
 def test_unknown_path_rejected(self):
  h=Capture('/nope',{});h.do_POST()
  self.assertEqual(h.response[0],404)
if __name__=='__main__':unittest.main()

