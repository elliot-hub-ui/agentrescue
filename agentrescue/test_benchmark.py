import json, pathlib, unittest
from app import diagnose
CASES=json.loads((pathlib.Path(__file__).resolve().parent/'benchmark.json').read_text())
class Benchmark(unittest.TestCase):
 def test_seeded_synthetic_cases(self):
  misses=[(x['error'],x['expected'],diagnose(x['error'])['category']) for x in CASES if diagnose(x['error'])['category']!=x['expected']]
  self.assertEqual(misses,[])
if __name__=='__main__': unittest.main()
