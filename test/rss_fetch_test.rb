# frozen_string_literal: true

require "minitest/autorun"
require "tempfile"

require_relative "../skills/summarize-feeds/scripts/rss_fetch"

class OPMLFeedLoaderTest < Minitest::Test
  def test_loads_flat_opml_with_xml_escaping
    feeds = load_opml(<<~XML)
        <?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <head><title>Example</title></head>
          <body>
            <outline
              type="rss"
              text="日本語 &amp; XML"
              title="日本語 &amp; XML"
              xmlUrl="https://example.com/feed?first=1&amp;second=2"
              htmlUrl="https://example.com/?first=1&amp;second=2" />
          </body>
        </opml>
      XML

    assert_equal([{ name: "日本語 & XML", url: "https://example.com/feed?first=1&second=2" }], feeds)
  end

  def test_loads_nested_opml_in_document_order
    feeds = load_opml(<<~XML)
        <opml version="2.0">
          <head><title>Nested</title></head>
          <body>
            <outline text="Group">
              <outline text="First" xmlUrl="https://example.com/first" />
              <outline text="Nested group">
                <outline
                  text="Second"
                  xmlUrl="https://example.com/second"
                  unexpected="ignored" />
              </outline>
            </outline>
            <outline text="Third" xmlUrl="https://example.com/third" />
          </body>
        </opml>
      XML

    assert_equal(%w[First Second Third], feeds.map { |feed| feed[:name] })
    assert_equal(
      %w[https://example.com/first https://example.com/second https://example.com/third],
      feeds.map { |feed| feed[:url] }
    )
  end

  def test_rejects_invalid_opml_configurations
    invalid_documents = [
      "feeds:\n- name: YAML",
      "<opml",
      "<feeds />",
      <<~XML,
        <opml version="1.0">
          <body><outline text="Feed" xmlUrl="https://example.com/feed" /></body>
        </opml>
      XML
      "<opml version=\"2.0\" />",
      <<~XML,
        <opml version="2.0">
          <body><outline text="Empty group" /></body>
        </opml>
      XML
      <<~XML,
        <opml version="2.0">
          <body><outline xmlUrl="https://example.com/feed" /></body>
        </opml>
      XML
      <<~XML
        <opml version="2.0">
          <body><outline text="Feed" xmlUrl=" " /></body>
        </opml>
      XML
    ]

    invalid_documents.each { |document| assert_raises(RuntimeError) { load_opml(document) } }
  end

  private

  def load_opml(document)
    Tempfile.create(%w[feeds .opml]) do |file|
      file.write(document)
      file.flush

      OPMLFeedLoader.load(file.path)
    end
  end
end

class RSSFetchTest < Minitest::Test
  RDF_XML = <<~XML
  <?xml version="1.0"?>
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
XML

  RSS_XML = <<~XML
  <?xml version="1.0"?>
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
XML

  ATOM_XML = <<~XML
  <?xml version="1.0"?>
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
XML

  def test_parses_rss_1
    items = collect_items(RDF_XML)

    assert_equal(2, items.length)
    assert_equal(
      {
        title: "First",
        link: "https://example.com/first.html",
        published: "2026-08-10T12:00:00+00:00",
        summary: "Summary 1"
      },
      items.first
    )
    assert_equal(
      {
        title: "Second",
        link: "https://example.com/second.html",
        published: "2026-08-09T12:00:00+00:00",
        summary: "Summary 2"
      },
      items[1]
    )
  end

  def test_parses_rss_2
    items = collect_items(RSS_XML)

    assert_equal(2, items.length)
    assert_equal(
      {
        title: "First",
        link: "https://example.com/first.html",
        published: "2026-08-10T12:00:00+00:00",
        summary: "Summary 1"
      },
      items.first
    )
    assert_equal(
      {
        title: "Second",
        link: "https://example.com/second.html",
        published: "2026-08-09T12:00:00+00:00",
        summary: "Summary 2"
      },
      items[1]
    )
  end

  def test_parses_atom
    items = collect_items(ATOM_XML)

    assert_equal(2, items.length)
    assert_equal(
      {
        title: "First",
        link: "https://example.com/first.html",
        published: "2026-08-10T12:00:00+00:00",
        summary: "Summary 1"
      },
      items.first
    )
    assert_equal(
      {
        title: "Second",
        link: "https://example.com/second.html",
        published: "2026-08-09T12:00:00+00:00",
        summary: "Summary 2"
      },
      items[1]
    )
  end

  def test_excludes_rss_items_without_publication_date
    rss = <<~XML
      <rss version="2.0">
        <channel>
          <title>Example RSS 2.0</title>
          <link>https://example.com/</link>
          <description>Example RSS 2.0 feed</description>
          <item>
            <title>Dated</title>
            <link>https://example.com/dated</link>
            <pubDate>Sun, 10 Aug 2026 12:00:00 GMT</pubDate>
          </item>
          <item>
            <title>Undated</title>
            <link>https://example.com/undated</link>
          </item>
        </channel>
      </rss>
    XML

    items = collect_items(rss)

    assert_equal(["Dated"], items.map { |item| item[:title] })
  end

  def test_excludes_atom_items_without_publication_date
    atom = <<~XML
      <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Example Atom</title>
        <link href="https://example.com"></link>
        <entry>
          <title>Dated</title>
          <link href="https://example.com/dated" />
          <updated>2026-08-10T12:00:00Z</updated>
        </entry>
        <entry>
          <title>Undated</title>
          <link href="https://example.com/undated" />
        </entry>
      </feed>
    XML

    items = collect_items(atom)

    assert_equal(["Dated"], items.map { |item| item[:title] })
  end

  def test_truncates_atom_summary_over_max_length
    summary = "あ" * 1_001
    atom = <<~XML
      <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Example Atom</title>
        <link href="https://example.com"></link>
        <entry>
          <title>Long summary</title>
          <link href="https://example.com/long-summary" />
          <updated>2026-08-10T12:00:00Z</updated>
          <summary>#{summary}</summary>
        </entry>
      </feed>
    XML

    items = collect_items(atom)

    assert_equal("あ" * 1_000, items.first[:summary])
  end

  def test_preserves_atom_summary_at_max_length
    summary = "あ" * 1_000
    atom = <<~XML
      <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Example Atom</title>
        <link href="https://example.com"></link>
        <entry>
          <title>Long summary</title>
          <link href="https://example.com/long-summary" />
          <updated>2026-08-10T12:00:00Z</updated>
          <summary>#{summary}</summary>
        </entry>
      </feed>
    XML

    items = collect_items(atom)

    assert_equal(summary, items.first[:summary])
  end

  def test_truncates_rss_summary_over_max_length
    summary = "あ" * 1_001
    rss = <<~XML
      <rss version="2.0">
        <channel>
          <title>Example RSS 2.0</title>
          <link>https://example.com/</link>
          <description>Example RSS 2.0 feed</description>
          <item>
            <title>Long summary</title>
            <link>https://example.com/long-summary</link>
            <pubDate>Sun, 10 Aug 2026 12:00:00 GMT</pubDate>
            <description>#{summary}</description>
          </item>
        </channel>
      </rss>
    XML

    items = collect_items(rss)

    assert_equal("あ" * 1_000, items.first[:summary])
  end

  def test_parses_atom_published_and_content_fallback
    content = "あ" * 1_001
    atom = <<~XML
      <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Example Atom</title>
        <link href="https://example.com"></link>
        <entry>
          <title>Content only</title>
          <published>2026-08-09T12:00:00Z</published>
          <content>#{content}</content>
        </entry>
      </feed>
    XML

    items = collect_items(atom)

    assert_equal("2026-08-09T12:00:00+00:00", items.first[:published])
    assert_equal("あ" * 1_000, items.first[:summary])
  end

  def test_uses_injected_feed_fetcher
    requested_urls = []
    feed_fetcher = Object.new
    feed_fetcher.define_singleton_method(:fetch) do |url|
      requested_urls << url
      RSS_XML
    end
    config = { feeds: [{ name: "RSS", url: "https://example.com/rss" }] }

    result = RSSFetch.new(**config, feed_fetcher: feed_fetcher).collect_feeds(progress: false)

    refute_predicate(result, :errors?)
    assert_equal(["https://example.com/rss"], requested_urls)
    assert_equal(2, result.feeds.first[:items].length)
  end

  def test_rejects_feed_fetcher_without_fetch
    error =
      assert_raises(ArgumentError) do
        RSSFetch.new(feeds: [{ name: "RSS", url: "https://example.com/rss" }], feed_fetcher: Object.new)
      end

    assert_equal("feed_fetcher must respond to fetch", error.message)
  end

  def test_rejects_invalid_constructor_arguments
    valid_feeds = [{ name: "RSS", url: "https://example.com/rss" }]
    invalid_arguments = [
      [{ feeds: [] }, "feeds must be a non-empty array"],
      [{ feeds: ["invalid"] }, "feeds[0] must be an object"],
      [{ feeds: [{ name: " ", url: "https://example.com/rss" }] }, "feeds[0].name must be a non-empty string"],
      [{ feeds: [{ name: "RSS", url: nil }] }, "feeds[0].url must be a non-empty string"]
    ]

    invalid_arguments.each do |arguments, expected_message|
      error = assert_raises(ArgumentError) { RSSFetch.new(**arguments) }

      assert_equal(expected_message, error.message)
    end
  end

  def test_rejects_invalid_collect_arguments
    rss_fetch = RSSFetch.new(feeds: [{ name: "RSS", url: "https://example.com/rss" }])
    invalid_arguments = [
      [{ item_limit: 0 }, "item_limit must be a positive integer"],
      [{ item_limit: "1" }, "item_limit must be a positive integer"],
      [{ max_age_days: -1 }, "max_age_days must be a non-negative integer"],
      [{ max_age_days: "1" }, "max_age_days must be a non-negative integer"]
    ]

    invalid_arguments.each do |arguments, expected_message|
      error = assert_raises(ArgumentError) { rss_fetch.collect_feeds(**arguments, progress: false) }

      assert_equal(expected_message, error.message)
    end
  end

  def test_applies_item_limit
    config = { feeds: [{ name: "RSS", url: "https://example.com/rss" }] }

    rss_fetch = RSSFetch.new(**config, feed_fetcher: sequential_fetcher(RSS_XML))

    result = rss_fetch.collect_feeds(item_limit: 1, progress: false)

    refute_predicate(result, :errors?)
    assert_equal(1, result.feeds.first[:items].length)
    assert_empty(result.errors)
  end

  def test_includes_item_exactly_at_cutoff
    dated_rss = <<~XML
      <rss version="2.0">
        <channel>
          <title>Example RSS 2.0</title>
          <link>https://example.com/</link>
          <item>
            <title>Boundary</title>
            <pubDate>Sat, 08 Aug 2026 12:00:00 GMT</pubDate>
          </item>
        </channel>
      </rss>
    XML
    config = { feeds: [{ name: "RSS", url: "https://example.com/rss" }] }
    rss_fetch = RSSFetch.new(**config, feed_fetcher: sequential_fetcher(dated_rss))

    result = rss_fetch.collect_feeds(max_age_days: 2, now: Time.utc(2026, 8, 10, 12), progress: false)

    assert_equal(["Boundary"], result.feeds.first[:items].map { |item| item[:title] })
  end

  def test_collect_filters_do_not_persist_between_runs
    rss_fetch =
      RSSFetch.new(
        feeds: [{ name: "RSS", url: "https://example.com/rss" }],
        feed_fetcher: sequential_fetcher(RSS_XML, RSS_XML, RSS_XML)
      )

    limited = rss_fetch.collect_feeds(item_limit: 1, progress: false)
    recent = rss_fetch.collect_feeds(max_age_days: 0, now: Time.utc(2026, 8, 10, 12), progress: false)
    unlimited = rss_fetch.collect_feeds(progress: false)

    assert_equal(1, limited.feeds.first[:items].length)
    assert_equal(["First"], recent.feeds.first[:items].map { |item| item[:title] })
    assert_equal(2, unlimited.feeds.first[:items].length)
  end

  def test_applies_age_filter_before_item_limit
    rss = <<~XML
      <rss version="2.0">
        <channel>
          <title>Example RSS 2.0</title>
          <link>https://example.com/</link>
          <description>Example RSS 2.0 feed</description>
          <item>
            <title>Old first</title>
            <pubDate>Sat, 01 Aug 2026 12:00:00 GMT</pubDate>
          </item>
          <item>
            <title>Recent second</title>
            <pubDate>Mon, 10 Aug 2026 12:00:00 GMT</pubDate>
          </item>
        </channel>
      </rss>
    XML
    rss_fetch =
      RSSFetch.new(feeds: [{ name: "RSS", url: "https://example.com/rss" }], feed_fetcher: sequential_fetcher(rss))

    result = rss_fetch.collect_feeds(item_limit: 1, max_age_days: 2, now: Time.utc(2026, 8, 10, 12), progress: false)

    assert_equal(["Recent second"], result.feeds.first[:items].map { |item| item[:title] })
  end

  def test_continues_after_http_and_parse_errors
    config = {
      feeds: [
        { name: "Good", url: "https://example.com/good" },
        { name: "HTTP error", url: "https://example.com/http-error" },
        { name: "Bad XML", url: "https://example.com/bad-xml" },
        { name: "Unsupported", url: "https://example.com/unsupported" }
      ]
    }
    fetcher = sequential_fetcher(RSS_XML, RSSFetch::FetchError.new("fetch error: unavailable"), "<rss>", "<html />")
    rss_fetch = RSSFetch.new(**config, feed_fetcher: fetcher)

    result = rss_fetch.collect_feeds(progress: false)

    assert_predicate(result, :errors?)
    assert_equal(["Good"], result.feeds.map { |feed| feed[:name] })
    assert_equal(["HTTP error", "Bad XML", "Unsupported"], result.errors.map { |error| error[:name] })
  end

  def test_preserves_feed_and_error_output_schema
    config = {
      feeds: [{ name: "Good", url: "https://example.com/good" }, { name: "Bad", url: "https://example.com/bad" }]
    }
    fetcher = sequential_fetcher(RSS_XML, RSSFetch::FetchError.new("fetch error: unavailable"))
    rss_fetch = RSSFetch.new(**config, feed_fetcher: fetcher)

    result = rss_fetch.collect_feeds(progress: false)

    assert_predicate(result, :errors?)
    assert_equal(
      {
        name: "Good",
        url: "https://example.com/good",
        items: [
          {
            title: "First",
            link: "https://example.com/first.html",
            published: "2026-08-10T12:00:00+00:00",
            summary: "Summary 1"
          },
          {
            title: "Second",
            link: "https://example.com/second.html",
            published: "2026-08-09T12:00:00+00:00",
            summary: "Summary 2"
          }
        ]
      },
      result.feeds.first
    )
    assert_equal([{ name: "Bad", url: "https://example.com/bad", error: "fetch error: unavailable" }], result.errors)
  end

  def test_does_not_convert_unexpected_fetcher_errors
    fetcher = sequential_fetcher(RuntimeError.new("implementation error"))
    rss_fetch = RSSFetch.new(feeds: [{ name: "RSS", url: "https://example.com/rss" }], feed_fetcher: fetcher)

    error = assert_raises(RuntimeError) { rss_fetch.collect_feeds(progress: false) }

    assert_equal("implementation error", error.message)
  end

  private

  def collect_items(data)
    fetcher = Object.new
    fetcher.define_singleton_method(:fetch) { |_url| data }
    config = { feeds: [{ name: "Feed", url: "https://example.com/feed" }] }
    result = RSSFetch.new(**config, feed_fetcher: fetcher).collect_feeds(progress: false)

    result.feeds.first[:items]
  end

  def sequential_fetcher(*responses)
    fetcher = Object.new
    fetcher.define_singleton_method(:fetch) do |_url|
      response = responses.shift
      raise response if response.is_a?(Exception)

      response
    end
    fetcher
  end
end
