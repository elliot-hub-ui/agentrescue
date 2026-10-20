import unittest
from app import SCHEMA, diagnose
class T(unittest.TestCase):
 def test_redacts_common_credentials_and_private_material(self):
  examples=['401 token=secret-value','Authorization: Bearer abcdefghijklmnop','ghp_abcdefghijklmnopqrstuvwxyz1234567890','AKIA1234567890ABCDEF','eyJabcdefgh.abcdefgh.abcdefgh','-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----','jane@example.com','postgres://admin:db-password@db.example.test/app','xoxb-1234567890abcdef','sk_live_1234567890abcdefghijkl','AIza12345678901234567890123456789012','aws_secret_access_key=some_secret_value']
  for value in examples:
   with self.subTest(value=value): self.assertNotIn(value,diagnose('failure '+value)['summary'])
 def test_safety_gate(self):
  x=diagnose('403');self.assertTrue(x['recovery']['requires_human_approval']);self.assertFalse(x['recovery']['execute_automatically'])
 def test_unknown(self):self.assertEqual(diagnose('odd')['category'],'unknown')
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
if __name__=='__main__':unittest.main()
