import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'research-report'
spec = importlib.util.spec_from_file_location('report_renderer', SKILL / 'scripts' / 'render_html.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class InputAndResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / '报告 示例.html'
        self.source.write_text('<html></html>', encoding='utf-8')

    def test_valid_input_with_unicode_and_spaces(self):
        html, output, roots = renderer.resolve_inputs(self.source, self.root / 'new', [])
        self.assertEqual(html, self.source)
        self.assertEqual(roots, [self.root])
        self.assertFalse(output.exists())

    def test_existing_output_is_preserved(self):
        output = self.root / 'existing'
        output.mkdir()
        sentinel = output / 'keep.txt'
        sentinel.write_text('original', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            renderer.resolve_inputs(self.source, output, [])
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'original')

    def test_non_html_input_rejected(self):
        source = self.root / 'source.txt'
        source.write_text('plain text', encoding='utf-8')
        with self.assertRaises(ValueError):
            renderer.resolve_inputs(source, self.root / 'new', [])

    def test_network_blocked(self):
        for url in ['https://example.org/image.png', 'http://example.org/a', 'ftp://example.org/a']:
            self.assertFalse(renderer.allowed_resource(url, [self.root]))

    def test_local_resource_allowed(self):
        self.assertTrue(renderer.allowed_resource(self.source.as_uri(), [self.root]))

    def test_parent_escape_blocked(self):
        self.assertFalse(renderer.allowed_resource((self.root.parent / 'private.txt').as_uri(), [self.root]))

    def test_symlink_escape_blocked(self):
        link = self.root / 'outside'
        try:
            link.symlink_to(self.root.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks are unavailable.')
        self.assertFalse(renderer.allowed_resource((link / 'private.txt').as_uri(), [self.root]))

    def test_inline_asset_allowed(self):
        self.assertTrue(renderer.allowed_resource('data:image/png;base64,AAAA', [self.root]))

    def test_cli_invalid_input_returns_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            result = renderer.main([str(self.source), '--output-dir', str(self.root / 'new'), '--max-pages', '0'])
        self.assertEqual(result, 1)
        self.assertFalse((self.root / 'new').exists())


@unittest.skipUnless(os.environ.get('REPORT_RENDER_TESTS') == '1', 'Set REPORT_RENDER_TESTS=1 to run browser tests.')
class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assets = self.root / 'input'
        shutil.copytree(SKILL / 'assets' / 'html', self.assets)
        self.html = self.assets / 'example.html'

    def run_render(self):
        output = self.root / 'output'
        html, output, roots = renderer.resolve_inputs(self.html, output, [])
        result = renderer.render(html, output, roots, os.environ.get('REPORT_BROWSER'))
        return result, output

    def change(self, old, new):
        content = self.html.read_text(encoding='utf-8')
        self.assertIn(old, content)
        self.html.write_text(content.replace(old, new, 1), encoding='utf-8')

    def test_example_exports_searchable_two_page_a4_pdf(self):
        from pypdf import PdfReader
        result, output = self.run_render()
        self.assertEqual(result['status'], 'passed', result['problems'])
        self.assertEqual(result['visual_review'], 'required')
        self.assertEqual(len(list(output.glob('page-*.png'))), 2)
        reader = PdfReader(output / 'report.pdf')
        self.assertEqual(len(reader.pages), 2)
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=1.0)
            self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=1.0)
        text = ''.join(''.join(page.extract_text().split()) for page in reader.pages)
        self.assertIn('资料整理与核验报告', text)
        self.assertIn('94.00%', text)
        self.assertGreater(len(text), 600)
        self.assertGreater(result['local_file_links_omitted'], 0)
        for page in reader.pages:
            for annotation in page.get('/Annots', []):
                uri = annotation.get_object().get('/A', {}).get('/URI', '')
                self.assertFalse(str(uri).startswith('file:'))

    def test_overflow_fails_without_exporting_pdf(self):
        self.change('</main>', '<p>' + '这一段用于验证内容超出页面时会停止导出。' * 250 + '</p></main>')
        result, output = self.run_render()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any(p['issue'] == 'text-overflow' for p in result['problems']))
        self.assertFalse((output / 'report.pdf').exists())
        self.assertTrue((output / 'layout-check.json').exists())

    def test_network_image_is_blocked_and_rejected(self):
        self.change('</main>', '<img src="https://example.invalid/picture.png" alt="示例"></main>')
        result, output = self.run_render()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['blocked_resources'])
        self.assertFalse((output / 'report.pdf').exists())

    def test_vertical_table_rules_are_rejected(self):
        self.change('</head>', '<style>td {border-left: 2px solid black !important}</style></head>')
        result, output = self.run_render()
        self.assertTrue(any(p['issue'] == 'table-vertical-rules' for p in result['problems']))
        self.assertFalse((output / 'report.pdf').exists())

    def test_heading_colliding_with_header_is_rejected(self):
        self.change('</head>', '<style>h1 {transform: translateY(-55px)}</style></head>')
        result, output = self.run_render()
        self.assertTrue(any(p['issue'] == 'text-overflow' for p in result['problems']))
        self.assertFalse((output / 'report.pdf').exists())


if __name__ == '__main__':
    unittest.main()
