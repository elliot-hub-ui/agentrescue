import io, json, unittest
from unittest import mock
from email.message import Message
import app
from app import H, MAX_RESPONSE_BYTES
class Capture(H):
 def __init__(self, path, payload):
  self.path=path; self.headers=Message(); raw=json.dumps(payload).encode(); self.headers['Content-Length']=str(len(raw)); self.rfile=io.BytesIO(raw); self.response=None
 def send(self,status,obj,typ='application/json'): self.response=(status,obj)
class RawCapture(Capture):
 def __init__(self,path,body=b'{}',headers=None):
  self.path=path;self.headers=Message()
  for key,value in (headers or {}).items():self.headers[key]=value
  self.rfile=io.BytesIO(body);self.response=None
class WireCapture(H):
 def __init__(self):self.wfile=io.BytesIO();self.out_headers={}
 def send_response(self,status):self.out_status=status
 def send_header(self,key,value):self.out_headers[key]=value
 def end_headers(self):pass
class HandlerTests(unittest.TestCase):
 def setUp(self):
  with app._rate_limit_lock:app._recent_posts.clear()
  with app._get_lock:app._recent_gets.clear()
 def test_llms_txt_explains_agent_safety_and_payment(self):
  h=Capture('/llms.txt',{});h.do_GET()
  self.assertEqual(h.response[0],200);self.assertIn('LLM',h.response[1].decode());self.assertIn('no-charge',h.response[1].decode())
 def test_homepage_links_the_agent_guide(self):
  h=Capture('/',{});h.do_GET()
  self.assertEqual(h.response[0],200)
  self.assertIn('href="/llms.txt"',h.response[1].decode())
 def test_tool_annotations_mark_read_only(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/list','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}});h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='tools/list';h.do_POST()
  ann=h.response[1]['result']['tools'][0]['annotations'];self.assertTrue(ann['readOnlyHint']);self.assertFalse(ann['destructiveHint'])
 def test_diagnosis_endpoint_response(self):
  h=Capture('/v1/diagnose',{'error':'MCP initialize invalid protocol version','system':'mcp'});h.do_POST()
  self.assertEqual(h.response[0],200); self.assertEqual(h.response[1]['category'],'mcp_protocol')
 def test_http_diagnosis_response_does_not_echo_input(self):
  marker='customer-run-id-8395 /internal/customer/acme'
  h=Capture('/v1/diagnose',{'error':'Unexpected upstream failure: '+marker});h.do_POST()
  self.assertEqual(h.response[0],200);self.assertNotIn(marker,json.dumps(h.response[1]))
 def test_mcp_diagnosis_response_does_not_echo_input(self):
  marker='customer-run-id-8395 /internal/customer/acme'
  h=Capture('/mcp',{'jsonrpc':'2.0','id':8,'method':'tools/call','params':{'name':'diagnose_failure','arguments':{'error':'Unexpected upstream failure: '+marker,'system':'mcp'},'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}})
  h.headers['MCP-Protocol-Version']='2026-07-28';h.headers['Mcp-Method']='tools/call';h.headers['Mcp-Name']='diagnose_failure';h.do_POST()
  self.assertEqual(h.response[0],200);self.assertNotIn(marker,json.dumps(h.response[1]))
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
 def test_feedback_is_disabled_by_default(self):
  with mock.patch.dict('os.environ',{},clear=True):
   h=Capture('/v1/feedback',{'opt_in':True});h.do_POST()
  self.assertEqual(h.response[0],404)
 def test_feedback_requires_explicit_opt_in_when_enabled(self):
  h=Capture('/v1/feedback',{'opt_in':False})
  with mock.patch.dict('os.environ',{'AGENTRESCUE_FEEDBACK_ENABLED':'true'}):h.do_POST()
  self.assertEqual(h.response[0],400);self.assertEqual(h.response[1]['error'],'explicit_opt_in_required')
 def test_feedback_rejects_freeform_values_and_extra_fields(self):
  value=Capture('/v1/feedback',{'opt_in':True,'category':'customer email alice@example.test','outcome':'resolved'})
  with mock.patch.dict('os.environ',{'AGENTRESCUE_FEEDBACK_ENABLED':'true'}):value.do_POST()
  self.assertEqual(value.response[0],400);self.assertEqual(value.response[1]['error'],'invalid_feedback_category')
  extra=Capture('/v1/feedback',{'opt_in':True,'category':'unknown','outcome':'unsure','diagnostic':'private text'})
  with mock.patch.dict('os.environ',{'AGENTRESCUE_FEEDBACK_ENABLED':'true'}):extra.do_POST()
  self.assertEqual(extra.response[0],400);self.assertEqual(extra.response[1]['error'],'unsupported_feedback_field')
 def test_feedback_stores_only_allowlisted_minimized_fields(self):
  h=Capture('/v1/feedback',{'opt_in':True,'category':'rate_limit','outcome':'resolved'})
  with mock.patch.dict('os.environ',{'AGENTRESCUE_FEEDBACK_ENABLED':'true'}), mock.patch('app.os.makedirs'), mock.patch('app.open',create=True) as open_mock, mock.patch('app.time.time',return_value=123):
   h.do_POST()
  self.assertEqual(h.response[0],201);self.assertEqual(open_mock.call_count,1)
  stored=open_mock.return_value.__enter__.return_value.write.call_args.args[0]
  self.assertEqual(json.loads(stored),{'category':'rate_limit','outcome':'resolved','at':123})
 def test_mcp_tools_call(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'diagnose_failure','arguments':{'error':'HTTP 429'}}});h.do_POST()
  self.assertEqual(h.response[0],200); self.assertEqual(h.response[1]['result']['structuredContent']['category'],'rate_limit')
 def test_mcp_rejects_bad_params_arguments_and_long_errors(self):
  params=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':[]});params.do_POST()
  self.assertEqual(params.response[1]['error']['code'],-32602);self.assertEqual(params.response[1]['error']['message'],'params must be an object')
  meta=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'_meta':[]}});meta.do_POST()
  self.assertEqual(meta.response[1]['error']['code'],-32602)
  args=Capture('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'arguments':[]}});args.do_POST()
  self.assertEqual(args.response[1]['error']['code'],-32602)
  long=Capture('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'arguments':{'error':'x'*8001}}});long.do_POST()
  self.assertEqual(long.response[1]['error']['code'],-32602)
 def test_mcp_null_params_is_valid_for_ping(self):
  h=Capture('/mcp',{'jsonrpc':'2.0','id':1,'method':'ping','params':None});h.do_POST()
  self.assertEqual(h.response[1]['result'],{})
 def test_mcp_rejects_non_jsonrpc_envelope(self):
  h=Capture('/mcp',{'id':1,'method':'ping'});h.do_POST()
  self.assertEqual(h.response[1]['error']['code'],-32600)
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
 def test_post_rate_limit_returns_retry_after(self):
  h=Capture('/v1/diagnose',{'error':'HTTP 429'})
  with mock.patch('app.allow_post',return_value=False):h.do_POST()
  self.assertEqual(h.response[0],429);self.assertEqual(h.response[1]['retry_after_seconds'],60)
 def test_get_rate_limit_returns_retry_after(self):
  h=Capture('/health',{})
  with mock.patch('app.allow_get',return_value=False):h.do_GET()
  self.assertEqual(h.response[0],429);self.assertEqual(h.response[1]['retry_after_seconds'],60)
 def test_outbound_response_has_a_hard_byte_ceiling(self):
  h=WireCapture();h.send(200,{'jsonrpc':'2.0','id':7,'result':{'oversized':'x'*MAX_RESPONSE_BYTES}})
  body=h.wfile.getvalue()
  self.assertLessEqual(len(body),MAX_RESPONSE_BYTES)
  self.assertEqual(json.loads(body)['error']['code'],-32603)
  self.assertEqual(int(h.out_headers['Content-Length']),len(body))
if __name__=='__main__':unittest.main()
