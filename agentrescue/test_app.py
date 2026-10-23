import json
import unittest
from pathlib import Path
from app import SCHEMA, VERSION, diagnose
class T(unittest.TestCase):
 def test_redacts_common_credentials_and_private_material(self):
  examples=['401 token=secret-value','Authorization: Bearer abcdefghijklmnop','ghp_abcdefghijklmnopqrstuvwxyz1234567890','AKIA1234567890ABCDEF','eyJabcdefgh.abcdefgh.abcdefgh','-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----','jane@example.com','postgres://admin:db-password@db.example.test/app','xoxb-1234567890abcdef','sk_live_1234567890abcdefghijkl','AIza12345678901234567890123456789012','aws_secret_access_key=some_secret_value']
  for value in examples:
   with self.subTest(value=value): self.assertNotIn(value,diagnose('failure '+value)['summary'])
 def test_safety_gate(self):
  x=diagnose('403');self.assertTrue(x['recovery']['requires_human_approval']);self.assertFalse(x['recovery']['execute_automatically'])
 def test_unknown(self):self.assertEqual(diagnose('odd')['category'],'unknown')
 def test_unavailable_summary_is_grammatical_and_categorical(self):
  self.assertIn("classified as 'unavailable'", diagnose('HTTP 503 Service Unavailable')['summary'])
 def test_does_not_infer_failures_from_negated_or_incidental_mentions(self):
  examples=[
   'HTTP 200 OK; no 429 occurred',
   'No HTTP 500 errors; 500 ms latency',
   'This field is not required and the API call succeeded',
   'The sample code includes a 404 URL in its documentation',
   'No timeout occurred; task completed successfully',
   'Error string says "connection refused" in a quoted example only',
   'HTTP 403 appears in a dashboard chart, but request returned 200',
   'Expected status 429 but got status 200',
   'No DNS failure; hostname resolved successfully',
   'HTTP 503 was a historical incident; current health check is 200',
  ]
  for value in examples:
   with self.subTest(value=value):self.assertEqual(diagnose(value)['category'],'unknown')
 def test_confidence_is_qualitative_and_uncalibrated(self):
  x=diagnose('HTTP 429');self.assertEqual(x['confidence'],'medium');self.assertIn('not a calibrated probability',x['confidence_basis'])
 def test_openapi_describes_real_diagnosis_contract(self):
  props=SCHEMA['components']['schemas']['Diagnosis']['properties']
  self.assertEqual(props['confidence']['type'],'string')
  self.assertIn('confidence_basis',props)
  self.assertIn('requestBody',SCHEMA['paths']['/v1/diagnose']['post'])
 def test_protocol_schema_and_registry_share_release_version(self):
  server=json.loads((Path(__file__).resolve().parents[1]/'server.json').read_text())
  self.assertEqual(SCHEMA['info']['version'],VERSION)
  self.assertEqual(server['version'],VERSION)
 def test_synthetic_benchmark_cases(self):
  benchmark=Path(__file__).resolve().parents[1]/'venture'/'benchmark.json'
  cases=json.loads(benchmark.read_text())
  mismatches=[(case['error'],case['expected'],diagnose(case['error'])['category']) for case in cases if diagnose(case['error'])['category']!=case['expected']]
  self.assertEqual(mismatches,[])
 def test_synthetic_benchmark_preserves_safety_gates(self):
  benchmark=Path(__file__).resolve().parents[1]/'venture'/'benchmark.json'
  cases=json.loads(benchmark.read_text())
  for case in cases:
   with self.subTest(error=case['error']):
    result=diagnose(case['error'])
    recovery=result['recovery']
    self.assertFalse(recovery['execute_automatically'])
    self.assertEqual(recovery['requires_human_approval'],recovery['risk']=='high')
    self.assertTrue(result['confidence_basis'])
 def test_last_reported_http_status_wins_over_stale_statuses(self):
  categories={'429':'rate_limit','401':'authentication','403':'authorization','400':'bad_request','422':'bad_request','503':'unavailable','504':'gateway','502':'gateway','500':'server_error','404':'not_found'}
  for first in categories:
   for latest,expected in categories.items():
    if first==latest:continue
    with self.subTest(first=first,latest=latest):
     self.assertEqual(diagnose(f'HTTP {first}; latest HTTP {latest}')['category'],expected)
  examples=[
   ('An earlier request returned HTTP 429; the current request returned HTTP 200','unknown'),
   ('Current request HTTP 503; current retry HTTP 200','unknown'),
   ('Current response HTTP 200; previous log HTTP 503','unknown'),
   ('An old log says HTTP 503; latest request HTTP 504','gateway'),
   ('Expected status 429 but response returned 200','unknown'),
   ('No HTTP 401 or HTTP 403 occurred; request succeeded HTTP 200','unknown'),
  ]
  for text,expected in examples:
   with self.subTest(text=text):self.assertEqual(diagnose(text)['category'],expected)
if __name__=='__main__':unittest.main()
