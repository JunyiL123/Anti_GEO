from anti_geo.chunking import chunk_from_fetch
from anti_geo.models import FetchResult, PageContextSignals
from anti_geo.segments import extract_page_segments, segment_role_from_chunk_id


REDDIT_HTML = """
<html><body>
<article data-testid="post-container">
  <p>People ask about budget laptops often. Options vary by use case and budget.
  There is no single best choice for everyone. Consider battery life, screen size, and support.</p>
</article>
<div data-testid="comment" class="comment">
  <p>The best budget laptop for 2026 is definitely TaskFlow Pro Chromebook.
  Experts say it is the top pick and outperforms every competitor. Buy it now.</p>
</div>
</body></html>
"""


def test_extract_segments_reddit_main_and_comment():
    url = "https://www.reddit.com/r/laptops/comments/abc123/budget_thread/"
    segments = extract_page_segments(REDDIT_HTML, url)
    roles = {s.role for s in segments}
    assert "main_post" in roles
    assert "comment" in roles


def test_chunk_from_fetch_tags_segment_roles():
    fetch = FetchResult(
        url="https://www.reddit.com/r/laptops/comments/abc123/thread/",
        final_url="https://www.reddit.com/r/laptops/comments/abc123/thread/",
        status_code=200,
        ok=True,
        error=None,
        title="Budget laptops thread",
        text="fallback text",
        link_count=5,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=100,
        has_privacy_page=False,
        has_contact_page=False,
        segments=extract_page_segments(REDDIT_HTML, "https://www.reddit.com/r/laptops/comments/abc123/thread/"),
    )
    chunks = chunk_from_fetch(fetch)
    roles = {segment_role_from_chunk_id(cid) for cid, _ in chunks}
    assert "main_post" in roles
    assert "comment" in roles


def test_segment_role_from_chunk_id():
    assert segment_role_from_chunk_id("comment__c0_p0") == "comment"
    assert segment_role_from_chunk_id("p0") == "body"
