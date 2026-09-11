import tempfile
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import render_site


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.ids = Counter()
        self.panels = Counter()
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids[attrs['id']] += 1
        if attrs.get('data-mobile-panel'):
            self.panels[attrs['data-mobile-panel']] += 1


class ResponsiveShellTests(unittest.TestCase):
    def test_every_view_has_one_result_target_and_reuses_controls(self):
        fixture = Path(__file__).parent / 'fixtures/signals-bundle.v1.json'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            render_site.render_site(fixture, output)
            for view, filename, _ in render_site.NAV_ITEMS:
                with self.subTest(view=view):
                    source = (output / filename).read_text()
                    elements = Elements(source)
                    for ident in ['viewSwitcher', 'pageInfo', 'dashboard-results', 'main-content']:
                        self.assertEqual(elements.ids[ident], 1)
                    self.assertLessEqual(elements.ids['search'], 1)
                    self.assertGreater(elements.panels['filters'], 0)
                    self.assertGreater(elements.panels['info'], 0)
                    self.assertIn('href="#dashboard-results"', source)
                    self.assertIn(f'data-dashboard-view="{view}"', source)

    def test_annotations_do_not_rewrite_embedded_script_strings(self):
        source = '<body><div class="tablewrap"><table></table></div><script>const html=\'<div class="kpis">unchanged</div>\';</script></body>'
        result = render_site._ResponsiveMarkup(source, 'shortlist').rendered()
        self.assertIn("const html='<div class=\"kpis\">unchanged</div>';", result)
        self.assertNotIn('data-mobile-panel', result)
