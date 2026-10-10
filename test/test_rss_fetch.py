"""Offline contract tests; no third-party test runner or live feeds required."""

from contextlib import redirect_stderr
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import socket

import feedparser

SCRIPT = Path(__file__).resolve().parents[1] / "skills/summarize-feeds/scripts/rss_fetch.py"
sys.path.insert(0, str(SCRIPT.parent))
from rss_fetch import FeedError, OPMLFeedLoader, RSSFetch

RDF_XML = """<?xml version="1.0"?>
<rdf:RDF
  xmlns="http://purl.org/rss/1.0/"
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.com/feed.rdf">
    <title>Example RSS 1.0/RDF</title>
    <link>https://example.com/</link>
    <description>Example RSS 1.0/RDF feed</description>
    <items>
      <rdf:Seq>
        <rdf:li rdf:resource="https://example.com/1" />
        <rdf:li rdf:resource="https://example.com/2" />
      </rdf:Seq>
    </items>
  </channel>
  <item rdf:about="https://example.com/1">
    <title>First</title>
    <link>https://example.com/first.html</link>
    <dc:date>2026-08-10T12:00:00Z</dc:date>
    <description>Summary 1</description>
  </item>
  <item rdf:about="https://example.com/2">
    <title>Second</title>
    <link>https://example.com/second.html</link>
    <dc:date>2026-08-09T12:00:00Z</dc:date>
    <description>Summary 2</description>
  </item>
</rdf:RDF>
"""

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example RSS 2.0</title>
    <link>https://example.com/</link>
    <description>Example RSS 2.0 feed</description>
    <item>
      <title>First</title>
      <link>https://example.com/first.html</link>
      <pubDate>Sun, 10 Aug 2026 12:00:00 GMT</pubDate>
      <description>Summary 1</description>
    </item>
    <item>
      <title>Second</title>
      <link>https://example.com/second.html</link>
      <pubDate>Sun, 9 Aug 2026 12:00:00 GMT</pubDate>
      <description>Summary 2</description>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <link href="https://example.com"></link>
  <entry>
    <title>First</title>
    <link rel="self" href="https://example.com/first" />
    <link rel="alternate" href="https://example.com/first.html" />
    <updated>2026-08-10T12:00:00Z</updated>
    <summary>Summary 1</summary>
  </entry>
  <entry>
    <title>Second</title>
    <link rel="self" href="https://example.com/second" />
    <link rel="alternate" href="https://example.com/second.html" />
    <updated>2026-08-09T12:00:00Z</updated>
    <summary>Summary 2</summary>
  </entry>
</feed>
"""

class SequentialParser:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.urls = []

    def parse(self, url):
        self.urls.append(url)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return response
        data = response.encode("utf-8") if isinstance(response, str) else response
        return feedparser.parse(io.BytesIO(data))


def collector(*responses):
    return RSSFetch(feeds=[{"name": "Feed", "url": "https://example.com/feed"}],
                    feed_parser=SequentialParser(*responses))


def items(xml, **options):
    result = collector(xml).collect_feeds(progress=False, **options)
    if result.errors:
        raise AssertionError(result.errors)
    return result.feeds[0]["items"]


def rss(fields, channel='<title>Feed</title><link>https://example.com</link>'):
    return ('<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            f'<channel>{channel}{fields}</channel></rss>')


def atom(fields):
    return f'<feed xmlns="http://www.w3.org/2005/Atom"><entry>{fields}</entry></feed>'


DATE = '<pubDate>Sun, 10 Aug 2026 12:00:00 GMT</pubDate>'
ATOM_DATE = '<updated>2026-08-10T12:00:00Z</updated>'
NOW = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)


class OPMLFeedLoaderTest(unittest.TestCase):
    def load_opml(self, xml):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'feeds.opml'
            path.write_text(xml, encoding='utf-8')
            return OPMLFeedLoader.load(path)

    def test_loads_flat_opml_with_xml_escaping(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0"><head><title>Example</title></head><body>
          <outline text="日本語 &amp; XML" xmlUrl="https://example.com/feed?first=1&amp;second=2" />
        </body></opml>'''
        self.assertEqual([{'name': '日本語 & XML', 'url': 'https://example.com/feed?first=1&second=2'}],
                         self.load_opml(xml))

    def test_loads_nested_opml_in_document_order(self):
        xml = '''<opml version="2.0"><body>
          <outline text="Group"><outline text="First" xmlUrl="https://example.com/first" />
            <outline text="Nested group"><outline text="Second" xmlUrl="https://example.com/second"
              unexpected="ignored" /></outline></outline>
          <outline text="Third" xmlUrl="https://example.com/third" />
        </body></opml>'''
        self.assertEqual([{'name': name, 'url': f'https://example.com/{name.lower()}'}
                          for name in ['First', 'Second', 'Third']], self.load_opml(xml))

    def test_feed_outlines_can_have_children_and_preserve_whitespace(self):
        xml = '''<opml version="2.0"><body><outline text=" Parent " xmlUrl=" https://example.com ">
          <outline text="Child" xmlUrl="https://example.com/child" /></outline></body></opml>'''
        self.assertEqual([' Parent ', 'Child'], [feed['name'] for feed in self.load_opml(xml)])
        self.assertEqual(' https://example.com ', self.load_opml(xml)[0]['url'])

    def test_rejects_invalid_opml_configurations(self):
        for xml in ['feeds:\n- name: YAML', '<opml', '<feeds/>',
                    '<opml version="1.0"><body/></opml>', '<opml version="2.0"/>',
                    '<opml version="2.0"><body><outline text="Empty group"/></body></opml>',
                    '<opml version="2.0"><body><outline xmlUrl="https://example.com"/></body></opml>',
                    '<opml version="2.0"><body><outline text="Feed" xmlUrl=" "/></body></opml>']:
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                self.load_opml(xml)


class RSSFetchTest(unittest.TestCase):
    def test_parses_rss_1_rss_2_and_atom(self):
        expected = [dict(title=title, link=f'https://example.com/{title.lower()}.html',
                         published=f'2026-08-{day}T12:00:00+00:00', summary=f'Summary {index}')
                    for index, (title, day) in enumerate([('First', '10'), ('Second', '09')], 1)]
        for xml in [RDF_XML, RSS_XML, ATOM_XML]:
            with self.subTest(xml=xml):
                self.assertEqual(expected, items(xml))

    def test_excludes_items_without_publication_date(self):
        fixtures = [rss('<item><title>Dated</title>' + DATE + '</item><item><title>Undated</title></item>'),
                    atom('<title>Dated</title>' + ATOM_DATE).replace('</feed>',
                         '<entry><title>Undated</title></entry></feed>')]
        for xml in fixtures:
            with self.subTest(xml=xml):
                self.assertEqual(['Dated'], [item['title'] for item in items(xml)])

    def test_summary_length_and_unicode(self):
        for length in [999, 1000, 1001]:
            for summary in ['あ' * length, '🌏' * length]:
                fixtures = [atom(ATOM_DATE + f'<summary>{summary}</summary>'),
                            rss('<item><title>Long</title>' + DATE + f'<description>{summary}</description></item>')]
                for xml in fixtures:
                    with self.subTest(length=length, xml=xml[:80]):
                        self.assertEqual(summary[:1000], items(xml)[0]['summary'])

    def test_parses_atom_published_and_content_fallback(self):
        xml = atom('<published>2026-08-09T12:00:00Z</published>' + ATOM_DATE + '<content>' + 'あ' * 1001 + '</content>')
        self.assertEqual('2026-08-09T12:00:00+00:00', items(xml)[0]['published'])
        self.assertEqual('あ' * 1000, items(xml)[0]['summary'])

    def test_empty_summary_does_not_fall_back(self):
        for xml in [atom(ATOM_DATE + '<summary/><content>Fallback</content>'),
                    rss('<item><title>X</title>' + DATE + '<description/><content:encoded>Fallback</content:encoded></item>')]:
            self.assertEqual('', items(xml)[0]['summary'])

    def test_html_cdata_and_rss_content_fallback(self):
        xml = rss('<item><title> X &amp; Y </title>' + DATE +
                  '<content:encoded><![CDATA[ <p>A &amp; B</p> ]]></content:encoded></item>')
        self.assertEqual('X & Y', items(xml)[0]['title'])
        self.assertEqual('<p>A &amp; B</p>', items(xml)[0]['summary'])
        self.assertEqual('<b>A & B</b>', items(atom(ATOM_DATE +
                         '<summary type="html">&lt;b&gt;A &amp; B&lt;/b&gt;</summary>'))[0]['summary'])

    def test_atom_xhtml_and_binary_content(self):
        markup = '<div xmlns="http://www.w3.org/1999/xhtml">A <b>B</b> C</div>'
        self.assertEqual('A <b>B</b> C', items(atom(ATOM_DATE + f'<summary type="xhtml">{markup}</summary>'))[0]['summary'])
        self.assertEqual('Hello', items(atom(ATOM_DATE + '<content type="image/png">SGVsbG8=</content>'))[0]['summary'])
        self.assertEqual('', items(atom(ATOM_DATE + '<content src="https://example.com/body" type="text/plain"/>'))[0]['summary'])

    def test_atom_xhtml_is_normalized(self):
        xml = atom(ATOM_DATE + '<summary type="xhtml" xmlns:h="http://www.w3.org/1999/xhtml">'
                   '<h:div><h:b>A &amp; B</h:b><h:br/></h:div></summary>')
        expected = '<b>A &amp; B</b><br />'
        self.assertEqual(expected, items(xml)[0]['summary'])

    def test_date_format_fallbacks_and_rollover(self):
        for date, expected in [(' 2026-08-10T12:00:00Z ', '2026-08-10T12:00:00+00:00'),
                               ('2026-08-10T24:00:00Z', '2026-08-11T00:00:00+00:00'),
                               ('2026-08-10T12:00:60Z', '2026-08-10T12:01:00+00:00'),
                               ('Sun, 10 Aug 2026 12:00:00 GMT', '2026-08-10T12:00:00+00:00')]:
            with self.subTest(date=date):
                self.assertEqual(expected, items(atom(f'<updated>{date}</updated>'))[0]['published'])
        xml = rss('<item><title>X</title><pubDate>2026-08-10T12:00:00Z</pubDate></item>')
        self.assertEqual('2026-08-10T12:00:00+00:00', items(xml)[0]['published'])

    def test_duplicate_scalar_fields_follow_feedparser(self):
        for xml in [atom(ATOM_DATE + '<title>First</title><title>Last</title>'),
                    rss('<item>' + DATE + '<title>First</title><title>Last</title></item>')]:
            self.assertEqual('First', items(xml)[0]['title'])

    def test_feed_encoding_declaration(self):
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?>' + atom(ATOM_DATE + '<title>Café</title>')
        self.assertEqual('Café', items(xml.encode('iso-8859-1'))[0]['title'])

    def test_atom_link_selection(self):
        for links, expected in [('<link rel="self" href="self"/><link href=" default "/>', 'default'),
                                ('<link rel="self" href=" first "/><link rel="alternate" href=" "/>', ''),
                                ('<link href=" "/>', ''), ('', '')]:
            with self.subTest(links=links):
                self.assertEqual(expected, items(atom(ATOM_DATE + links))[0]['link'])

    def test_namespace_prefixes_and_unrelated_elements(self):
        xml = '<a:feed xmlns:a="http://www.w3.org/2005/Atom" xmlns:x="urn:other"><a:entry>' + \
              '<x:title>Wrong</x:title><a:title>Right</a:title><a:updated>2026-08-10T12:00:00Z</a:updated>' + \
              '</a:entry><x:entry><x:title>Wrong entry</x:title></x:entry></a:feed>'
        self.assertEqual(['Right'], [item['title'] for item in items(xml)])

    def test_dates_and_offsets(self):
        for date in ['2026-08-10T21:00:00+09:00', '2026-08-10T12:00:00.999Z', '2026-08-10T12:00:00']:
            with self.subTest(date=date):
                self.assertEqual('2026-08-10T12:00:00+00:00', items(atom(f'<updated>{date}</updated>'))[0]['published'])
        self.assertEqual('2026-08-10T12:00:00+00:00', items(atom('<published>invalid</published>' + ATOM_DATE))[0]['published'])
        self.assertEqual([], items(atom('<updated>invalid</updated>')))
        self.assertEqual([], items(rss('<item><title>X</title><pubDate>invalid</pubDate></item>')))
        self.assertEqual('2026-08-10T12:00:00+00:00',
                         items(rss('<item><title>X</title><dc:date>2026-08-10T12:00:00Z</dc:date></item>'))[0]['published'])

    def test_preserves_order_and_duplicate_articles(self):
        xml = rss('<item><title>Old</title><pubDate>Sun, 9 Aug 2026 12:00:00 GMT</pubDate></item>' +
                  '<item><title>New</title>' + DATE + '</item>' + '<item><title>New</title>' + DATE + '</item>')
        self.assertEqual(['Old', 'New', 'New'], [item['title'] for item in items(xml)])

    def test_uses_injected_feed_parser(self):
        fetcher = SequentialParser(RSS_XML)
        result = RSSFetch(feeds=[{'name': 'RSS', 'url': 'https://example.com/rss'}],
                          feed_parser=fetcher).collect_feeds(progress=False)
        self.assertFalse(result.has_errors())
        self.assertEqual(['https://example.com/rss'], fetcher.urls)
        self.assertEqual(2, len(result.feeds[0]['items']))

    def test_rejects_feed_parser_without_parse(self):
        with self.assertRaisesRegex(ValueError, 'feed_parser must respond to parse'):
            RSSFetch(feeds=[{'name': 'RSS', 'url': 'https://example.com/rss'}], feed_parser=object())

    def test_rejects_invalid_constructor_arguments(self):
        for feeds, message in [(None, 'feeds must be a non-empty array'), ([], 'feeds must be a non-empty array'),
                               (['invalid'], 'feeds[0] must be an object'),
                               ([{'name': ' ', 'url': 'https://example.com'}], 'feeds[0].name must be a non-empty string'),
                               ([{'name': 'RSS', 'url': None}], 'feeds[0].url must be a non-empty string')]:
            with self.subTest(feeds=feeds), self.assertRaises(ValueError) as error:
                RSSFetch(feeds=feeds)
            self.assertEqual(message, str(error.exception))

    def test_rejects_invalid_collect_arguments(self):
        for name, values, message in [('item_limit', [0, -1, '1', True, 1.5], 'item_limit must be a positive integer'),
                                     ('max_age_days', [-1, '1', True, 1.5], 'max_age_days must be a non-negative integer')]:
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError) as error:
                    collector().collect_feeds(**{name: value}, progress=False)
                self.assertEqual(message, str(error.exception))

    def test_applies_item_limit(self):
        self.assertEqual(1, len(items(RSS_XML, item_limit=1)))

    def test_includes_item_exactly_at_cutoff(self):
        self.assertEqual(['First', 'Second'], [item['title'] for item in items(RSS_XML, max_age_days=1, now=NOW)])
        self.assertEqual(['First'], [item['title'] for item in items(RSS_XML, max_age_days=0, now=NOW)])

    def test_collect_filters_do_not_persist_between_runs(self):
        fetch = collector(RSS_XML, RSS_XML, RSS_XML)
        self.assertEqual(1, len(fetch.collect_feeds(item_limit=1, progress=False).feeds[0]['items']))
        self.assertEqual(1, len(fetch.collect_feeds(max_age_days=0, now=NOW, progress=False).feeds[0]['items']))
        self.assertEqual(2, len(fetch.collect_feeds(progress=False).feeds[0]['items']))

    def test_applies_age_filter_before_item_limit(self):
        xml = rss('<item><title>Old</title><pubDate>Sat, 01 Aug 2026 12:00:00 GMT</pubDate></item>' +
                  '<item><title>Recent</title>' + DATE + '</item>')
        self.assertEqual(['Recent'], [item['title'] for item in items(xml, item_limit=1, max_age_days=2, now=NOW)])

    def test_continues_after_http_and_parse_errors(self):
        names = ['Good', 'HTTP error', 'Bad XML', 'Unsupported']
        result = RSSFetch(feeds=[dict(name=name, url='https://example.com') for name in names],
                          feed_parser=SequentialParser(RSS_XML, OSError('unavailable'),
                                                         '<rss>', '<html/>')).collect_feeds(progress=False)
        self.assertTrue(result.has_errors())
        self.assertEqual(['Good'], [feed['name'] for feed in result.feeds])
        self.assertEqual(names[1:], [feed['name'] for feed in result.errors])
        self.assertTrue(result.errors[1]['error'].startswith('invalid feed: '))
        self.assertEqual('unsupported feed format (expected RSS or Atom)', result.errors[2]['error'])

    def test_preserves_feed_and_error_output_schema(self):
        result = RSSFetch(feeds=[dict(name='Good', url='good'), dict(name='Bad', url='bad')],
                          feed_parser=SequentialParser(RSS_XML, OSError('unavailable'))
                          ).collect_feeds(progress=False)
        self.assertEqual({'feeds': [dict(name='Good', url='good', items=items(RSS_XML))],
                          'errors': [dict(name='Bad', url='bad', error='fetch error: unavailable')]}, result.to_dict())

    def test_missing_rss_metadata_is_accepted(self):
        for channel in ['', '<title>Feed</title>', '<link>https://example.com</link>']:
            with self.subTest(channel=channel):
                self.assertEqual([dict(title='', link='', published='2026-08-10T12:00:00+00:00', summary='')],
                                 items(rss('<item>' + DATE + '</item>', channel)))

    def test_rejects_malformed_feed_even_with_recoverable_entries(self):
        result = collector(RSS_XML.replace('</channel>', '')).collect_feeds(progress=False)
        self.assertEqual([], result.feeds)
        self.assertEqual(1, len(result.errors))
        self.assertTrue(result.errors[0]['error'].startswith('invalid feed: '))

    def test_does_not_convert_unexpected_fetcher_errors(self):
        with self.assertRaisesRegex(RuntimeError, 'implementation error'):
            collector(RuntimeError('implementation error')).collect_feeds(progress=False)

    def test_progress_is_written_only_to_stderr(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            collector(RSS_XML).collect_feeds()
        self.assertEqual('Fetching: Feed\n', stderr.getvalue())


class CLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/rss')
                    self.end_headers()
                    return
                if self.path == '/missing':
                    self.send_error(404)
                    return
                self.send_response(503 if self.path == "/server-error" else 200)
                self.send_header("Content-Type", "application/xml; charset=utf-8")
                self.end_headers()
                self.wfile.write({'/rss': RSS_XML, '/atom': ATOM_XML, '/bad': '<rss>', '/server-error': RSS_XML}.get(self.path, '<html/>').encode())

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_cli(self, *arguments):
        return subprocess.run(['uv', 'run', '--script', str(SCRIPT), *arguments],
                              capture_output=True, text=True, timeout=10)

    def config(self, directory, *paths):
        path = Path(directory) / 'feeds.opml'
        path.write_text('<opml version="2.0"><body>' + ''.join(
            f'<outline text="{route}" xmlUrl="{self.url}{route}"/>' for route in paths) + '</body></opml>')
        return str(path)

    def test_help_and_argument_errors(self):
        help_result = self.run_cli('--help')
        self.assertEqual(0, help_result.returncode)
        self.assertTrue(help_result.stdout.startswith('Usage: rss_fetch.py '))
        self.assertEqual('', help_result.stderr)
        for args in [(), ('--bad',), ('--item-limit',), ('--item-limit', '0', 'config'),
                     ('--item-limit', 'nope', 'config'), ('--max-age-days', '-1', 'config'), ('a', 'b')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(2, result.returncode)
                self.assertEqual('', result.stdout)
                self.assertTrue(result.stderr.startswith('Argument error: '))
                self.assertIn(help_result.stdout, result.stderr)

    def test_cli_integer_forms_and_validation_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config(directory, '/rss')
            for value, expected in [('010', 8), ('0x10', 16), ('0b10', 2), ('1_000', 1000), ('+1', 1)]:
                result = self.run_cli('--item-limit', value, path)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn(f'item_limit={expected} ', result.stderr)
            for value in ['08', '0o10', '1.0', ' 1 ']:
                result = self.run_cli('--item-limit', value, path)
                self.assertEqual(2, result.returncode)
                self.assertTrue(result.stderr.startswith(f'Argument error: invalid argument: --item-limit {value}\n'))
        result = self.run_cli('--item-limit', '0')
        self.assertTrue(result.stderr.startswith(
            'Argument error: invalid argument: --item-limit --item-limit must be a positive integer\n'))

    def test_configuration_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'feeds.opml'
            for data in [None, b'<opml', b'<opml version="1.0"/>', b'\xff']:
                if data is not None:
                    path.write_bytes(data)
                result = self.run_cli(str(path))
                self.assertEqual(2, result.returncode)
                self.assertEqual('', result.stdout)
                self.assertTrue(result.stderr.startswith('Configuration error: '))

    def test_success_json_progress_and_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config(directory, '/rss', '/redirect')
            result = self.run_cli('--item-limit', '1', path)
        self.assertEqual(0, result.returncode, result.stderr)
        expected = {'feeds': [dict(name=route, url=self.url + route, items=items(RSS_XML, item_limit=1))
                              for route in ['/rss', '/redirect']], 'errors': []}
        self.assertEqual(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', result.stdout)
        self.assertEqual(f'Start: config={path} feeds=2 item_limit=1 max_age_days=unlimited\n'
                         'Fetching: /rss\nFetching: /redirect\nComplete: articles=2\n', result.stderr)

    def test_partial_and_total_feed_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            for routes in [('/missing', '/atom', '/bad'), ('/missing',)]:
                with self.subTest(routes=routes):
                    result = self.run_cli(self.config(directory, *routes))
                    self.assertEqual(1, result.returncode)
                    data = json.loads(result.stdout)
                    self.assertEqual([route for route in routes if route == '/atom'],
                                     [feed['name'] for feed in data['feeds']])
                    self.assertEqual('fetch error: 404 Not Found', data['errors'][0]['error'])

    def test_connection_failure(self):
        # Reserve a port without listening so the connection fails immediately.
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            url = f'http://127.0.0.1:{reserved.getsockname()[1]}/feed'
            result = RSSFetch(feeds=[dict(name='Unavailable', url=url)]).collect_feeds(progress=False)
        self.assertEqual([], result.feeds)
        self.assertEqual(1, len(result.errors))
        self.assertTrue(result.errors[0]['error'].startswith('fetch error: '))

    def test_http_error_with_valid_feed_body_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(self.config(directory, '/server-error'))
        self.assertEqual(1, result.returncode)
        data = json.loads(result.stdout)
        self.assertEqual([], data['feeds'])
        self.assertEqual('fetch error: 503 Service Unavailable', data['errors'][0]['error'])


if __name__ == '__main__':
    unittest.main()
