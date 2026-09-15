from scholar_radar.fetch import html_to_page

HTML = """
<html><head><title>MSc AI Scholarship 2027</title><script>var x=1;</script></head>
<body>
  <nav>Home | About</nav>
  <h1>Fully funded MSc in Artificial Intelligence</h1>
  <p>Deadline: 15 January 2027</p>
  <a href="/apply">Apply now</a>
  <a href="https://other.org/info#section">More info</a>
  <footer>Copyright</footer>
</body></html>
"""


def test_html_to_page_extracts_clean_text_and_links():
    page = html_to_page(HTML, "https://uni.example.edu/programs/ai")
    assert page.title == "MSc AI Scholarship 2027"
    assert "Fully funded MSc in Artificial Intelligence" in page.text
    assert "Deadline: 15 January 2027" in page.text
    assert "var x" not in page.text
    assert "Home | About" not in page.text
    assert "Copyright" not in page.text
    assert ("Apply now", "https://uni.example.edu/apply") in page.links
    assert ("More info", "https://other.org/info") in page.links


def test_html_to_page_truncates():
    page = html_to_page("<p>" + "a" * 500 + "</p>", "https://x.org", max_chars=100)
    assert len(page.text) == 100
