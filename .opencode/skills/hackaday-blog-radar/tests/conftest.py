import sys
from pathlib import Path

import pytest

_skill_root = Path(__file__).parent.parent
_src = _skill_root / "src"
sys.path.insert(0, str(_skill_root))
sys.path.insert(0, str(_src))


@pytest.fixture
def sample_archive_html() -> str:
    return """<!DOCTYPE html>
<html>
<body>
<section id="primary" class="content-area">
<main id="main" class="site-main" role="main">
<header class="page-header">
    <h1 class="page-title">LED Hacks<h2 class="counter_cat">1935 Articles</h2></h1>
</header>
<article class="post type-post status-publish format-standard hentry category-led-hacks">
    <header class="entry-header">
        <h1 class="entry-title"><a href="https://hackaday.com/2024/01/15/test-article-1/" rel="bookmark">Test LED PWM Fading Article</a></h1>
        <div class="entry-meta">
            <span class="entry-date"><a href="https://hackaday.com/2024/01/15/">January 15, 2024</a></span>
        </div>
    </header>
    <div class="entry-content"><p>Using PWM to control LED brightness for smooth fading effects on multiple LEDs.</p></div>
    <footer class="entry-footer">
        <span class="tags-links">Tagged <a rel="tag">led</a>, <a rel="tag">pwm</a></span>
    </footer>
</article>
<article class="post type-post status-publish format-standard hentry category-led-hacks">
    <header class="entry-header">
        <h1 class="entry-title"><a href="https://hackaday.com/2024/02/20/test-article-2/" rel="bookmark">WS2812B Addressable LED Strip Project</a></h1>
        <div class="entry-meta">
            <span class="entry-date"><a href="https://hackaday.com/2024/02/20/">February 20, 2024</a></span>
        </div>
    </header>
    <div class="entry-content"><p>Building a LED sculpture using addressable LEDs and an ESP32 microcontroller.</p></div>
    <footer class="entry-footer">
        <span class="tags-links">Tagged <a rel="tag">ws2812b</a>, <a rel="tag">addressable</a></span>
    </footer>
</article>
<article class="post type-post status-publish format-standard hentry category-led-hacks">
    <header class="entry-header">
        <h1 class="entry-title"><a href="https://hackaday.com/2023/11/05/test-article-3/" rel="bookmark">555 Timer LED Flasher Circuits</a></h1>
        <div class="entry-meta">
            <span class="entry-date"><a href="https://hackaday.com/2023/11/05/">November 5, 2023</a></span>
        </div>
    </header>
    <div class="entry-content"><p>Analog LED flasher circuits using the 555 timer, no MCU required.</p></div>
    <footer class="entry-footer">
        <span class="tags-links">Tagged <a rel="tag">555 timer</a>, <a rel="tag">analog</a></span>
    </footer>
</article>
</main>
</section>
</body>
</html>"""


@pytest.fixture
def sample_article_html() -> str:
    return """<!DOCTYPE html>
<html>
<body>
<article class="post type-post status-publish format-standard hentry category-led-hacks">
    <header class="entry-header">
        <h1 class="entry-title">Test LED PWM Fading Article</h1>
        <div class="entry-meta">
            <span class="author">By <a href="/author/testauthor/">Test Author</a></span>
            <span class="entry-date"><a href="https://hackaday.com/2024/01/15/">January 15, 2024</a></span>
        </div>
    </header>
    <div class="entry-content">
        <p>LED brightness control using PWM signals.</p>
        <p>More detailed content here.</p>
        <div class="sharedaddy">skip this</div>
        <div class="jp-relatedposts">skip this too</div>
    </div>
    <ol class="comment-list">
        <li class="comment">
            <cite class="fn">John Doe</cite>
            <a class="comment-permalink" href="#comment-1">January 16, 2024 at 10:00 am</a>
            <div class="comment-content"><p>Great article!</p></div>
        </li>
        <li class="comment">
            <cite class="fn">Jane Smith</cite>
            <a class="comment-permalink" href="#comment-2">January 17, 2024 at 2:30 pm</a>
            <div class="comment-content"><p>Very useful, thanks.</p></div>
        </li>
        <li class="comment"></li>
    </ol>
</article>
</body>
</html>"""


@pytest.fixture
def sample_article_no_author_html() -> str:
    return """<!DOCTYPE html>
<html>
<body>
<article class="post type-post status-publish format-standard hentry category-led-hacks">
    <header class="entry-header">
        <h1 class="entry-title">No Author Article</h1>
        <div class="entry-meta">
            <span class="entry-date"><a href="https://hackaday.com/2024/03/01/">March 1, 2024</a></span>
        </div>
    </header>
    <div class="entry-content"><p>Content without author.</p></div>
</article>
</body>
</html>"""


@pytest.fixture
def sample_article_disqus_html() -> str:
    return """<!DOCTYPE html>
<html>
<body>
<article class="post type-post status-publish format-standard hentry">
    <header class="entry-header">
        <h1 class="entry-title">Disqus Comments Article</h1>
    </header>
    <div class="entry-content"><p>Article with Disqus.</p></div>
<div id="disqus_thread"></div>
</article>
</body>
</html>"""