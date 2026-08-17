import base64
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE = ROOT / "functions" / "_middleware.js"


def run_middleware_probe(url: str) -> str:
    source_url = "data:text/javascript;base64," + base64.b64encode(
        MIDDLEWARE.read_bytes()
    ).decode("ascii")
    script = f"""
const middleware = await import({source_url!r});
let nextCalls = 0;
const response = await middleware.onRequest({{
  request: new Request({url!r}),
  next: async () => {{
    nextCalls += 1;
    return new Response("allowed", {{status: 200}});
  }},
}});
console.log(JSON.stringify({{status: response.status, nextCalls}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class EdgeAccessTests(unittest.TestCase):
    def test_custom_hostname_reaches_application(self):
        self.assertEqual(
            run_middleware_probe("https://screener.chiragpatnaik.com/market.html"),
            '{"status":200,"nextCalls":1}',
        )

    def test_pages_alias_is_denied_before_application(self):
        self.assertEqual(
            run_middleware_probe(
                "https://deployment.screener-bo9.pages.dev/api/refresh"
            ),
            '{"status":403,"nextCalls":0}',
        )


if __name__ == "__main__":
    unittest.main()
