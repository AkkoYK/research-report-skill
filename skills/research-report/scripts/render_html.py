#!/usr/bin/env python3
"""Render a locally authored, fixed-page HTML report with mechanical layout checks."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


LAYOUT_CHECK = r"""() => {
  const problems = [];
  const papers = [...document.querySelectorAll('.pdf-page')];
  const pages = papers.map((paper, index) => {
    const content = paper.querySelector('.page-content');
    const footer = paper.querySelector('.pdf-footer');
    if (!content || !footer) {
      problems.push({page: index + 1, issue: 'missing-content-or-footer'});
      return {number: index + 1};
    }
    const bounds = content.getBoundingClientRect();
    const header = paper.querySelector('.pdf-header');
    // Font metric boxes can extend above their line box without crossing the header.
    const top = header ? header.getBoundingClientRect().bottom + 8 : bounds.top;
    const bottom = footer.getBoundingClientRect().top - 8;
    let metricOverhang = 0;
    if (!content.textContent.trim() && !content.querySelector('img,svg'))
      problems.push({page: index + 1, issue: 'empty-content'});
    const elements = content.querySelectorAll('h1,h2,h3,p,li,td,th,caption,figcaption,pre,svg text');
    for (const element of elements) {
      const range = document.createRange();
      range.selectNodeContents(element);
      const box = range.getBoundingClientRect();
      metricOverhang = Math.max(metricOverhang, bounds.top - box.top);
      if (box.width && (box.left < bounds.left - 1 || box.right > bounds.right + 1 ||
          box.top < top - 1 || box.bottom > Math.min(bounds.bottom, bottom) + 1)) {
        problems.push({page: index + 1, issue: 'text-overflow', text: element.textContent.slice(0, 70),
          box: {top: box.top, right: box.right, bottom: box.bottom, left: box.left},
          limits: {top, right: bounds.right, bottom: Math.min(bounds.bottom, bottom), left: bounds.left}});
      }
    }
    for (const element of content.querySelectorAll('table,figure,img,svg,pre')) {
      const box = element.getBoundingClientRect();
      if (box.left < bounds.left - 1 || box.right > bounds.right + 1 ||
          box.top < top - 1 || box.bottom > Math.min(bounds.bottom, bottom) + 1)
        problems.push({page: index + 1, issue: 'element-overflow', element: element.tagName});
    }
    for (const img of content.querySelectorAll('img')) {
      if (!img.complete || img.naturalWidth === 0)
        problems.push({page: index + 1, issue: 'unloaded-image'});
    }
    for (const table of content.querySelectorAll('table')) {
      const style = getComputedStyle(table);
      const head = table.tHead && getComputedStyle(table.tHead);
      if (!table.caption || !head || parseFloat(style.borderTopWidth) <= 0 ||
          parseFloat(style.borderBottomWidth) <= 0 || parseFloat(head.borderBottomWidth) <= 0)
        problems.push({page: index + 1, issue: 'table-caption-or-three-rules-missing'});
      if ([...table.querySelectorAll('td,th')].some(cell => {
        const s = getComputedStyle(cell);
        return parseFloat(s.borderLeftWidth) > 0 || parseFloat(s.borderRightWidth) > 0;
      })) problems.push({page: index + 1, issue: 'table-vertical-rules'});
    }
    const last = content.lastElementChild;
    return {number: index + 1, width: paper.getBoundingClientRect().width,
      height: paper.getBoundingClientRect().height,
      usedHeight: last ? last.getBoundingClientRect().bottom - bounds.top : 0,
      availableHeight: bounds.height, fontMetricTopOverhang: metricOverhang};
  });
  return {pages, problems};
}"""


def resolve_inputs(html, output_dir, asset_roots):
    html = Path(html).expanduser().resolve(strict=True)
    if not html.is_file() or html.suffix.lower() not in {'.html', '.htm'}:
        raise ValueError('Input must be an existing HTML file.')
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise ValueError('Output directory already exists; choose a new directory.')
    roots = [html.parent]
    for item in asset_roots:
        root = Path(item).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Each asset root must be an existing directory.')
        roots.append(root)
    return html, output, roots


def allowed_resource(url, roots):
    parsed = urlparse(url)
    if parsed.scheme in {'data', 'blob'}:
        return True
    if parsed.scheme != 'file' or parsed.netloc not in {'', 'localhost'}:
        return False
    value = unquote(parsed.path)
    if sys.platform == 'win32' and len(value) > 2 and value[0] == '/' and value[2] == ':':
        value = value[1:]
    target = Path(value).resolve()
    return any(target == root or root in target.parents for root in roots)


def render(html, output, roots, executable_path=None, max_pages=100):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError('Install scripts/requirements.txt and a Playwright Chromium browser first.') from error

    blocked = []
    with sync_playwright() as playwright:
        options = {'headless': True}
        if executable_path:
            options['executable_path'] = str(Path(executable_path).expanduser().resolve(strict=True))
        browser = playwright.chromium.launch(**options)
        try:
            context = browser.new_context(
                viewport={'width': 1000, 'height': 1300}, device_scale_factor=2,
                java_script_enabled=False, service_workers='block',
            )

            def route_request(route):
                if allowed_resource(route.request.url, roots):
                    route.continue_()
                else:
                    blocked.append({'scheme': urlparse(route.request.url).scheme,
                                    'type': route.request.resource_type})
                    route.abort()

            context.route('**/*', route_request)
            page = context.new_page()
            page.goto(html.as_uri(), wait_until='load', timeout=30000)
            page.evaluate('() => document.fonts.ready')
            page.emulate_media(media='print')
            page_count = page.locator('.pdf-page').count()
            if not 1 <= page_count <= max_pages:
                raise ValueError(f'Expected 1–{max_pages} .pdf-page elements; found {page_count}.')
            result = page.evaluate(LAYOUT_CHECK)
            result['blocked_resources'] = blocked
            if blocked:
                result['problems'].append({'issue': 'blocked-external-resource', 'count': len(blocked)})

            cdp = context.new_cdp_session(page)
            cdp.send('DOM.enable')
            cdp.send('CSS.enable')
            root_node = cdp.send('DOM.getDocument')['root']['nodeId']
            fonts = {}
            for selector in ['h1', 'p', 'td']:
                node = cdp.send('DOM.querySelector', {'nodeId': root_node, 'selector': selector})['nodeId']
                if node:
                    fonts[selector] = cdp.send('CSS.getPlatformFontsForNode', {'nodeId': node})['fonts']
            result['fonts'] = fonts
            result['browser_version'] = browser.version
            result['status'] = 'failed' if result['problems'] else 'passed'
            result['visual_review'] = 'required'
            output.mkdir(parents=True, exist_ok=False)
            for index in range(page_count):
                filename = f'page-{index + 1:03d}.png'
                page.locator('.pdf-page').nth(index).screenshot(path=str(output / filename))
                result['pages'][index]['preview'] = filename
            if result['status'] == 'passed':
                result['local_file_links_omitted'] = page.evaluate(r"""() => {
                  let count = 0;
                  for (const link of document.querySelectorAll('a[href]')) {
                    const raw = link.getAttribute('href');
                    if (!raw.startsWith('#') && new URL(raw, document.baseURI).protocol === 'file:') {
                      link.removeAttribute('href');
                      count++;
                    }
                  }
                  return count;
                }""")
                page.pdf(path=str(output / 'report.pdf'), prefer_css_page_size=True,
                         print_background=True, display_header_footer=False, tagged=True, outline=True)
                result['pdf'] = 'report.pdf'
            (output / 'layout-check.json').write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
            )
            return result
        finally:
            browser.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--asset-root', action='append', default=[], type=Path,
                        help='Additional permitted local asset directory; may be repeated.')
    parser.add_argument('--executable-path', type=Path,
                        help='Optional installed Chrome/Chromium executable.')
    parser.add_argument('--max-pages', type=int, default=100)
    args = parser.parse_args(argv)
    try:
        if args.max_pages < 1:
            raise ValueError('--max-pages must be positive.')
        html, output, roots = resolve_inputs(args.html, args.output_dir, args.asset_root)
        result = render(html, output, roots, args.executable_path, args.max_pages)
        print(json.dumps({'status': result['status'], 'pages': len(result['pages']),
                          'problems': len(result['problems']), 'visual_review': 'required'},
                         ensure_ascii=False))
        return 0 if result['status'] == 'passed' else 2
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
