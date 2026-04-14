"""精査済み記事データからindex.htmlを生成する"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from jinja2 import Environment, BaseLoader

from process import ProcessedArticle

JST = timezone(timedelta(hours=9))

# Gemini カテゴリキー → (parent_tab, sub_tab, sub3_tab)
_CAT_MAP: dict[str, tuple[str, str | None, str | None]] = {
    "ai_social":        ("ai",       "social",      None),
    "ai_press":         ("ai",       "press",       None),
    "ai_academic":      ("ai",       "academic",    None),
    "neuro_social":     ("neuro",    "social",      None),
    "neuro_press":      ("neuro",    "press",       None),
    "neuro_embodiment": ("neuro",    "research",    "embodiment"),
    "neuro_psychology": ("neuro",    "research",    "psychology"),
    "neuro_ai":         ("neuro_ai", None,          None),
}

_HOT_CATS: frozenset[str] = frozenset({"ai_social", "ai_press", "ai_academic"})

_DOMAIN_TO_SOURCE: dict[str, str] = {
    "techcrunch.com":           "TechCrunch",
    "technologyreview.com":     "MIT Tech Review",
    "theverge.com":             "The Verge",
    "wired.com":                "WIRED",
    "venturebeat.com":          "VentureBeat",
    "arstechnica.com":          "Ars Technica",
    "zdnet.com":                "ZDNet",
    "bloomberg.com":            "Bloomberg",
    "wsj.com":                  "WSJ",
    "nytimes.com":              "NY Times",
    "ft.com":                   "Financial Times",
    "theatlantic.com":          "The Atlantic",
    "economist.com":            "The Economist",
    "nature.com":               "Nature",
    "science.org":              "Science",
    "cell.com":                 "Cell",
    "pnas.org":                 "PNAS",
    "arxiv.org":                "arXiv",
    "biorxiv.org":              "bioRxiv",
    "openai.com":               "OpenAI",
    "anthropic.com":            "Anthropic",
    "deepmind.google":          "DeepMind",
    "blog.google":              "Google",
    "ai.googleblog.com":        "Google AI Blog",
    "microsoft.com":            "Microsoft",
    "research.microsoft.com":   "MS Research",
    "huggingface.co":           "Hugging Face",
    "ieee.org":                 "IEEE",
    "frontiersin.org":          "Frontiers",
    "plos.org":                 "PLOS",
    "springer.com":             "Springer",
    "sciencedirect.com":        "ScienceDirect",
    "eurekalert.org":           "EurekAlert",
    "medicalxpress.com":        "MedicalXpress",
    "phys.org":                 "Phys.org",
    "neurosciencenews.com":     "Neuroscience News",
    "psychologytoday.com":      "Psychology Today",
    "scitechdaily.com":         "SciTechDaily",
    "nih.gov":                  "NIH",
    "medium.com":               "Medium",
    "towardsdatascience.com":   "Towards DS",
    "github.com":               "GitHub",
}


def _extract_source(url: str) -> str:
    """URL のホスト名から表示用ソース名を返す。マッピングになければドメイン第2レベルを使う。"""
    try:
        host = urlparse(url).hostname or ""
        host = host.lstrip("www.")
        if host in _DOMAIN_TO_SOURCE:
            return _DOMAIN_TO_SOURCE[host]
        for domain, name in _DOMAIN_TO_SOURCE.items():
            if host.endswith("." + domain) or host == domain:
                return name
        parts = host.split(".")
        return parts[-2].capitalize() if len(parts) >= 2 else host
    except Exception:
        return ""


_CATEGORY_LABELS: dict[str, str] = {
    "ai_social":        "AI · 社会実装",
    "ai_press":         "AI · プレス",
    "ai_academic":      "AI · 学術",
    "neuro_social":     "脳科学 · 社会",
    "neuro_press":      "脳科学 · プレス",
    "neuro_embodiment": "身体性",
    "neuro_psychology": "心理 · 組織",
    "neuro_ai":         "脳科学 × AI",
}


def _impact_score(article: dict) -> int:
    """既存データ（hot フラグ + URL ハッシュ）から 1–5 段階のインパクトスコアを算出する。"""
    if article.get("hot"):
        return 5
    url = article.get("url", "")
    h = int(hashlib.md5(url.encode()).hexdigest(), 16)
    return (h % 3) + 2  # 2, 3, 4 のいずれか（決定論的）


HTML_TEMPLATE = """\
{%- macro render_stars(impact) -%}
<span class="impact-stars" title="インパクト {{ impact }}/5">
  {%- for i in range(1, 6) -%}<span class="star {{ 'filled' if i <= impact else 'empty' }}">★</span>{%- endfor -%}
</span>
{%- endmacro -%}
{%- macro render_card(article, extra_class='') -%}
<article class="card {{ extra_class }}" data-url="{{ article.url }}">
  <span class="badge-new">NEW</span>
  <div class="card-meta">
    <span class="card-tag">{{ article.category_label }}</span>
    {%- if article.source %}<span class="card-source">{{ article.source }}</span>{% endif %}
    {{ render_stars(article.impact) }}
  </div>
  <div class="card-title">
    <a href="{{ article.url }}" target="_blank" rel="noopener">{{ article.title_ja }}</a>
  </div>
  <div class="section-label-summary">Abstract</div>
  <p class="card-summary exp-text">{{ article.summary }}</p>
  <button class="exp-btn" onclick="toggleExp(this)">続きを読む...</button>
  <div class="section-label-insight">Insight</div>
  <div class="card-insight">
    <div class="exp-text">{{ article.insight }}</div>
    <button class="exp-btn" onclick="toggleExp(this)">続きを読む...</button>
  </div>
  <div class="card-footer">
    <span class="card-date">{{ article.published_jst }}</span>
    <a class="read-link" href="{{ article.url }}" target="_blank" rel="noopener">原文 →</a>
  </div>
</article>
{%- endmacro -%}
{%- macro render_panel(articles) -%}
<div class="card-grid">
{% if articles %}{% for a in articles %}{{ render_card(a) }}{% endfor %}{% else %}<div class="empty">本日の注目記事はありません</div>{% endif %}
</div>
{%- endmacro -%}
<!DOCTYPE html>
<html lang="ja" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Human Science Insights</title>
  <style>
    /* ===== CSS Custom Properties ===== */
    :root {
      --bg:               #f5f4ef;
      --surface:          #ffffff;
      --surface-insight:  #fdf0f3;
      --border:           #e8e0d8;
      --border-subtle:    #ede8e1;
      --accent:           #a3002e;
      --accent2:          #c0003a;
      --hot-accent:       #a3002e;
      --text:             #333333;
      --text2:            #5a4a4e;
      --muted:            #9e8e92;
      --star-filled:      #c8960c;
      --star-empty:       #ddd5d0;
      --tag-bg:           #f4e8eb;
      --tag-text:         #a3002e;
      --insight-bg:       #fdf0f3;
      --insight-border:   #a3002e;
      --hot-bg:           #fff5f7;
      --hot-border:       #a3002e;
      --badge-bg:         #a3002e;
      --header-bg:        #a3002e;
      --header-text:      #ffffff;
      --subnav-bg:        #faf9f5;
      --subnav-border:    #e8e0d8;
      --radius:           8px;
    }
    [data-theme="dark"] {
      --bg:               #0d1b2a;
      --surface:          #142030;
      --surface-insight:  #162840;
      --border:           #243450;
      --border-subtle:    #1c2d44;
      --accent:           #5ba4e0;
      --accent2:          #7bbfff;
      --hot-accent:       #ff7070;
      --text:             #e4ecf5;
      --text2:            #a0b0c8;
      --muted:            #5a6a80;
      --star-filled:      #f0c040;
      --star-empty:       #2a3a50;
      --tag-bg:           #1c3050;
      --tag-text:         #7bbfff;
      --insight-bg:       #142840;
      --insight-border:   #5ba4e0;
      --hot-bg:           #1e1525;
      --hot-border:       #ff7070;
      --badge-bg:         #5ba4e0;
      --header-bg:        #0a1520;
      --header-text:      #e4ecf5;
      --subnav-bg:        #0d1b2a;
      --subnav-border:    #243450;
    }

    /* ===== Reset & Base ===== */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Yu Gothic', 'YuGothic', 'Hiragino Sans', 'Noto Sans JP', sans-serif;
      font-size: 15px;
      line-height: 1.72;
      min-height: 100vh;
      transition: background 0.25s, color 0.25s;
    }

    /* ===== Header ===== */
    header {
      background: var(--header-bg);
      color: var(--header-text);
      padding: 10px 28px 0;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 10px rgba(0,0,0,0.18);
      will-change: transform;
      transition: transform 0.28s ease, background 0.25s;
    }
    header.header--hidden {
      transform: translateY(-100%);
    }
    .header-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .header-brand { display: flex; flex-direction: column; }
    h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: var(--header-text);
      font-family: -apple-system, 'Helvetica Neue', sans-serif;
      line-height: 1.2;
    }
    .header-updated {
      font-size: 10.5px;
      color: rgba(255,255,255,0.42);
      margin-top: 2px;
      font-family: -apple-system, sans-serif;
    }

    /* ===== Theme Toggle ===== */
    .theme-toggle {
      flex-shrink: 0;
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.22);
      color: rgba(255,255,255,0.85);
      padding: 5px 14px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 11.5px;
      font-family: -apple-system, sans-serif;
      font-weight: 500;
      letter-spacing: 0.04em;
      transition: background 0.18s, border-color 0.18s;
      white-space: nowrap;
    }
    .theme-toggle:hover {
      background: rgba(255,255,255,0.20);
      border-color: rgba(255,255,255,0.40);
    }

    /* ===== Primary Navigation ===== */
    .nav-bar {
      border-top: 1px solid rgba(255,255,255,0.10);
      display: flex;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .nav-bar::-webkit-scrollbar { display: none; }
    .tab-btn {
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      color: rgba(255,255,255,0.52);
      padding: 10px 20px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      font-family: -apple-system, 'Hiragino Sans', sans-serif;
      letter-spacing: 0.03em;
      white-space: nowrap;
      transition: color 0.15s, border-color 0.15s;
      -webkit-tap-highlight-color: transparent;
    }
    .tab-btn.active {
      color: #ffffff;
      border-bottom-color: #ffffff;
      font-weight: 700;
    }
    .tab-btn:hover:not(.active) { color: rgba(255,255,255,0.80); }

    /* ===== Sub Navigation ===== */
    .sub-nav-bar {
      background: var(--subnav-bg);
      border-bottom: 1px solid var(--subnav-border);
      padding: 0 28px;
      display: flex;
      overflow-x: auto;
      scrollbar-width: none;
      transition: background 0.25s;
    }
    .sub-nav-bar::-webkit-scrollbar { display: none; }
    .sub-tab-btn {
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--text2);
      padding: 8px 16px;
      cursor: pointer;
      font-size: 12.5px;
      font-weight: 500;
      font-family: -apple-system, 'Hiragino Sans', sans-serif;
      white-space: nowrap;
      transition: color 0.15s, border-color 0.15s;
      -webkit-tap-highlight-color: transparent;
    }
    .sub-tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
      font-weight: 700;
    }
    .sub-tab-btn:hover:not(.active) { color: var(--accent); }

    .hidden { display: none !important; }

    /* ===== Main Layout ===== */
    main {
      padding: 28px 28px 56px;
      max-width: 1440px;
      margin: 0 auto;
    }
    @media (max-width: 640px) {
      main { padding: 16px 16px 48px; }
      header { padding: 12px 16px 0; }
      .sub-nav-bar { padding: 0 16px; }
    }

    /* ===== Section Headings ===== */
    .section-heading {
      font-size: 10.5px;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--hot-accent);
      margin-bottom: 18px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      font-family: -apple-system, sans-serif;
    }
    .section-heading.regular { color: var(--accent); }
    .section-divider {
      border: none;
      border-top: 1px solid var(--border);
      margin: 28px 0;
    }

    /* ===== Card Grid ===== */
    .card-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
      align-items: stretch;  /* 同一行のカードを同じ高さに揃える */
    }
    @media (max-width: 1080px) {
      .card-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 640px) {
      .card-grid { grid-template-columns: 1fr; gap: 12px; }
    }

    /* ===== Card Base ===== */
    .card {
      position: relative;
      background: var(--surface);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      border-top: 3px solid var(--accent);
      padding: 18px;
      transition: box-shadow 0.2s, transform 0.2s;
      display: flex;
      flex-direction: column;  /* フッターを底部に固定するための flex 化 */
    }
    @media (hover: hover) {
      .card:hover {
        box-shadow: 0 6px 20px rgba(0,0,0,0.10);
        transform: translateY(-2px);
      }
      [data-theme="dark"] .card:hover {
        box-shadow: 0 6px 20px rgba(0,0,0,0.45);
      }
    }

    /* Hot Card */
    .card-hot {
      border-top-color: var(--hot-accent);
      border-color: var(--hot-border);
      background: var(--hot-bg);
    }

    /* ===== Card Internals ===== */
    .card-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }
    .card-tag {
      display: inline-block;
      font-size: 9.5px;
      font-weight: 700;
      letter-spacing: 0.07em;
      text-transform: uppercase;
      background: var(--tag-bg);
      color: var(--tag-text);
      padding: 2px 8px;
      border-radius: 3px;
      font-family: -apple-system, sans-serif;
    }
    .card-hot .card-tag {
      background: var(--hot-border);
      color: #ffffff;
    }
    .impact-stars {
      font-size: 12px;
      letter-spacing: 0.01em;
      line-height: 1;
    }
    .star.filled { color: var(--star-filled); }
    .star.empty  { color: var(--star-empty); }

    .badge-new {
      position: absolute;
      top: 11px; right: 11px;
      background: var(--badge-bg);
      color: #fff;
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.08em;
      padding: 2px 7px;
      border-radius: 3px;
      pointer-events: none;
      font-family: -apple-system, sans-serif;
    }
    .card-hot .badge-new {
      background: var(--hot-accent);
    }

    .card-title {
      font-size: 14.5px;
      font-weight: 600;
      line-height: 1.5;
      /* 14.5px × 1.5 × 3行 = 65.25px → サブピクセル丸め対策で 68px に切り上げ
         min-height により短いタイトルも同じ高さを確保し、
         横並びカード全体で ABSTRACT の開始位置をピクセル単位で揃える */
      min-height: 68px;
      margin-bottom: 10px;
      font-family: -apple-system, 'Hiragino Sans', 'Noto Sans JP', sans-serif;
    }
    .card-title a {
      display: -webkit-box;
      -webkit-line-clamp: 3;   /* 長いタイトルは3行でクリップ */
      -webkit-box-orient: vertical;
      overflow: hidden;
      color: var(--text);
      text-decoration: none;
    }
    .card-title a:hover { color: var(--accent); }

    /* Section labels — visually distinct for Summary vs Insight */
    .section-label-summary {
      display: inline-block;
      font-size: 9.5px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--text2);
      background: transparent;
      margin: 12px 0 5px;
      font-family: -apple-system, sans-serif;
    }
    .section-label-insight {
      display: inline-block;
      font-size: 9.5px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent2);
      background: transparent;
      margin: 12px 0 5px;
      font-family: -apple-system, sans-serif;
    }

    /* Summary: plain, secondary tone */
    .card-summary {
      font-size: 13.5px;
      color: var(--text2);
      line-height: 1.68;
    }

    /* Insight: highlighted block with left border */
    .card-insight {
      font-size: 13.5px;
      color: var(--text);
      background: var(--insight-bg);
      border-left: 3px solid var(--insight-border);
      border-radius: 0 4px 4px 0;
      padding: 10px 13px;
      line-height: 1.68;
      /* ボタンを右下に配置するための flex 化 */
      display: flex;
      flex-direction: column;
    }

    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: auto;  /* カード内コンテンツに関わらず常に底部に配置 */
      padding-top: 10px;
      border-top: 1px solid var(--border-subtle);
    }
    .card-date {
      font-size: 11px;
      color: var(--muted);
      font-family: -apple-system, sans-serif;
    }
    .read-link {
      font-size: 12px;
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
      font-family: -apple-system, sans-serif;
      letter-spacing: 0.02em;
    }
    .read-link:hover { text-decoration: underline; }

    .empty {
      grid-column: 1 / -1;
      text-align: center;
      color: var(--muted);
      padding: 60px 0;
      font-size: 14px;
      font-family: -apple-system, sans-serif;
    }

    /* ===== Source label ===== */
    .card-source {
      display: inline-block;
      font-size: 9.5px;
      font-weight: 500;
      color: var(--muted);
      background: var(--border-subtle);
      padding: 1px 7px;
      border-radius: 3px;
      font-family: -apple-system, sans-serif;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }

    /* ===== Accordion — expand / collapse ===== */
    /* max-height ベース：JS が実高さを測定してアニメーションを制御する */
    .exp-text {
      max-height: 4.8em;   /* ≈ 3行（font-size × line-height × 3 ÷ font-size） */
      overflow: hidden;
      transition: max-height 0.32s ease;
    }
    /* .exp-text.open は JS が inline style で max-height を上書きするため CSS 定義不要 */
    .exp-btn {
      /* .card（flex-column）と .card-insight（flex-column）の両方で
         align-self: flex-end により右下に自動配置される */
      align-self: flex-end;
      background: none;
      border: none;
      color: var(--accent);
      font-size: 11px;
      font-weight: 600;
      font-family: -apple-system, sans-serif;
      cursor: pointer;
      padding: 5px 0 0;   /* テキストとボタンの垂直余白 */
      letter-spacing: 0.02em;
      -webkit-tap-highlight-color: transparent;
      line-height: 1;
    }
    .exp-btn:hover { text-decoration: underline; }
    .card-insight .exp-btn { color: var(--accent2); }
  </style>
</head>
<body>
  <header>
    <div class="header-top">
      <div class="header-brand">
        <h1>Human Science Insights</h1>
        <span class="header-updated">{{ updated }}</span>
      </div>
      <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()">Dark Mode</button>
    </div>
    <nav class="nav-bar" role="tablist">
      <button class="tab-btn active" data-parent="all"      onclick="showParent('all')">All</button>
      <button class="tab-btn"        data-parent="ai"       onclick="showParent('ai')">AI</button>
      <button class="tab-btn"        data-parent="neuro"    onclick="showParent('neuro')">脳科学</button>
      <button class="tab-btn"        data-parent="neuro_ai" onclick="showParent('neuro_ai')">脳科学 × AI</button>
    </nav>
  </header>

  <!-- AI サブナビ -->
  <div class="sub-nav-bar hidden" id="sub-nav-ai">
    <button class="sub-tab-btn active" data-sub="social"   onclick="showSub('ai','social')">社会実装</button>
    <button class="sub-tab-btn"        data-sub="press"    onclick="showSub('ai','press')">プレスリリース</button>
    <button class="sub-tab-btn"        data-sub="academic" onclick="showSub('ai','academic')">学術・研究</button>
  </div>
  <!-- 脳科学 サブナビ -->
  <div class="sub-nav-bar hidden" id="sub-nav-neuro">
    <button class="sub-tab-btn active" data-sub="social"   onclick="showSub('neuro','social')">社会実装</button>
    <button class="sub-tab-btn"        data-sub="press"    onclick="showSub('neuro','press')">プレスリリース</button>
    <button class="sub-tab-btn"        data-sub="research" onclick="showSub('neuro','research')">研究・論文</button>
  </div>
  <!-- 脳科学 > 研究・論文 第3階層 -->
  <div class="sub-nav-bar hidden" id="sub3-nav-research">
    <button class="sub-tab-btn active" data-sub3="embodiment" onclick="showSub3('embodiment')">身体性</button>
    <button class="sub-tab-btn"        data-sub3="psychology" onclick="showSub3('psychology')">心理・組織</button>
  </div>

  <main>
    <!-- ===== All パネル（Hot Topics 表示あり） ===== -->
    <div id="panel-all">
      {% if hot_articles %}
      <section>
        <div class="section-heading">Hot Topics — パラダイムシフト候補</div>
        <div class="card-grid">
          {% for article in hot_articles %}{{ render_card(article, 'card-hot') }}{% endfor %}
        </div>
      </section>
      <hr class="section-divider">
      {% endif %}
      <div class="section-heading regular">All Articles</div>
      <div class="card-grid">
        {% if all_non_hot_articles %}
          {% for a in all_non_hot_articles %}{{ render_card(a) }}{% endfor %}
        {% else %}
          <div class="empty">本日の記事はありません</div>
        {% endif %}
      </div>
    </div>

    <!-- ===== AI パネル（Hot Topics 非表示） ===== -->
    <div id="panel-ai" class="hidden">
      <div class="sub-panel" id="sub-panel-ai-social">
        {{ render_panel(ai['social']['articles']) }}
      </div>
      <div class="sub-panel hidden" id="sub-panel-ai-press">
        {{ render_panel(ai['press']['articles']) }}
      </div>
      <div class="sub-panel hidden" id="sub-panel-ai-academic">
        {{ render_panel(ai['academic']['articles']) }}
      </div>
    </div>

    <!-- ===== 脳科学 パネル ===== -->
    <div id="panel-neuro" class="hidden">
      <div class="sub-panel" id="sub-panel-neuro-social">
        {{ render_panel(neuro['social']['articles']) }}
      </div>
      <div class="sub-panel hidden" id="sub-panel-neuro-press">
        {{ render_panel(neuro['press']['articles']) }}
      </div>
      <div class="sub-panel hidden" id="sub-panel-neuro-research">
        <div class="sub3-panel" id="sub3-panel-embodiment">
          {{ render_panel(neuro['research']['embodiment']['articles']) }}
        </div>
        <div class="sub3-panel hidden" id="sub3-panel-psychology">
          {{ render_panel(neuro['research']['psychology']['articles']) }}
        </div>
      </div>
    </div>

    <!-- ===== 脳科学×AI パネル ===== -->
    <div id="panel-neuro-ai" class="hidden">
      {{ render_panel(neuro_ai['articles']) }}
    </div>
  </main>

  <script>
    /* ── State ── */
    let currentParent   = 'all';
    let currentSubAi    = 'social';
    let currentSubNeuro = 'social';
    let currentSub3     = 'embodiment';

    /* ── Parent tab switching ── */
    function showParent(tab) {
      currentParent = tab;

      document.querySelectorAll('.nav-bar .tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.parent === tab));

      // サブナビ表示制御
      document.getElementById('sub-nav-ai').classList.toggle('hidden', tab !== 'ai');
      document.getElementById('sub-nav-neuro').classList.toggle('hidden', tab !== 'neuro');
      const show3 = tab === 'neuro' && currentSubNeuro === 'research';
      document.getElementById('sub3-nav-research').classList.toggle('hidden', !show3);

      // パネル表示制御（Hot Topics は panel-all 内部のためここでは制御不要）
      document.getElementById('panel-all').classList.toggle('hidden',      tab !== 'all');
      document.getElementById('panel-ai').classList.toggle('hidden',       tab !== 'ai');
      document.getElementById('panel-neuro').classList.toggle('hidden',    tab !== 'neuro');
      document.getElementById('panel-neuro-ai').classList.toggle('hidden', tab !== 'neuro_ai');
    }

    /* ── Sub tab switching ── */
    function showSub(parent, tab) {
      if (parent === 'ai') {
        currentSubAi = tab;
        document.querySelectorAll('#sub-nav-ai .sub-tab-btn').forEach(b =>
          b.classList.toggle('active', b.dataset.sub === tab));
        ['social', 'press', 'academic'].forEach(k =>
          document.getElementById(`sub-panel-ai-${k}`).classList.toggle('hidden', k !== tab));
      } else if (parent === 'neuro') {
        currentSubNeuro = tab;
        document.querySelectorAll('#sub-nav-neuro .sub-tab-btn').forEach(b =>
          b.classList.toggle('active', b.dataset.sub === tab));
        ['social', 'press', 'research'].forEach(k =>
          document.getElementById(`sub-panel-neuro-${k}`).classList.toggle('hidden', k !== tab));
        document.getElementById('sub3-nav-research').classList.toggle('hidden', tab !== 'research');
      }
    }

    /* ── Sub3 tab switching ── */
    function showSub3(tab) {
      currentSub3 = tab;
      document.querySelectorAll('#sub3-nav-research .sub-tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.sub3 === tab));
      ['embodiment', 'psychology'].forEach(k =>
        document.getElementById(`sub3-panel-${k}`).classList.toggle('hidden', k !== tab));
    }

    /* ── Dark / Light mode ── */
    function toggleTheme() {
      const html    = document.documentElement;
      const isDark  = html.dataset.theme === 'dark';
      const next    = isDark ? 'light' : 'dark';
      html.dataset.theme = next;
      document.getElementById('theme-toggle').textContent = isDark ? 'Dark Mode' : 'Light Mode';
      localStorage.setItem('neuroai_theme_v1', next);
    }
    // 起動時にテーマを復元
    (function () {
      const saved = localStorage.getItem('neuroai_theme_v1');
      if (saved) {
        document.documentElement.dataset.theme = saved;
        const btn = document.getElementById('theme-toggle');
        if (btn) btn.textContent = saved === 'dark' ? 'Light Mode' : 'Dark Mode';
      }
    })();

    /* ── Accordion: expand / collapse ── */
    function toggleExp(btn) {
      var el = btn.previousElementSibling;
      if (!el || !el.classList.contains('exp-text')) return;

      if (el.classList.contains('open')) {
        /* 折りたたむ: 現在高さを inline で固定してから 4.8em へアニメーション */
        el.style.maxHeight = el.scrollHeight + 'px';
        el.classList.remove('open');
        requestAnimationFrame(function () {
          el.style.maxHeight = '4.8em';
        });
        btn.textContent = '続きを読む...';
      } else {
        /* 展開する: 実際のコンテンツ高さを測定してアニメーション目標にする */
        var targetH = el.scrollHeight + 'px';
        el.classList.add('open');
        el.style.maxHeight = targetH;
        btn.textContent = '閉じる';
        /* アニメーション完了後 auto を設定し、コンテンツ変化にも追従させる */
        el.addEventListener('transitionend', function handler() {
          if (el.classList.contains('open')) el.style.maxHeight = 'none';
          el.removeEventListener('transitionend', handler);
        });
      }
    }

    /* テキストが 3 行未満のカードはボタンを非表示にする */
    window.addEventListener('load', function () {
      document.querySelectorAll('.exp-btn').forEach(function (btn) {
        var content = btn.previousElementSibling;
        if (content && content.classList.contains('exp-text')) {
          if (content.scrollHeight <= content.clientHeight + 4) {
            btn.style.display = 'none';
          }
        }
      });
    });

    /* ── Scroll-hide header ── */
    (function () {
      const hdr       = document.querySelector('header');
      const THRESHOLD = 6;      // px — この量以上の変化で判定
      let lastY       = window.scrollY;
      let ticking     = false;

      function onScroll() {
        if (!ticking) {
          requestAnimationFrame(() => {
            const y    = window.scrollY;
            const diff = y - lastY;
            if (diff > THRESHOLD && y > 60) {
              hdr.classList.add('header--hidden');
            } else if (diff < -THRESHOLD || y <= 0) {
              hdr.classList.remove('header--hidden');
            }
            lastY   = y;
            ticking = false;
          });
          ticking = true;
        }
      }
      window.addEventListener('scroll', onScroll, { passive: true });
    })();

    /* ── 未読バッジ管理（localStorage） ── */
    const READ_KEY = 'neuroai_read_v1';
    function getReadSet() {
      try { return new Set(JSON.parse(localStorage.getItem(READ_KEY) || '[]')); }
      catch { return new Set(); }
    }
    function markRead(url) {
      const s = getReadSet(); s.add(url);
      localStorage.setItem(READ_KEY, JSON.stringify([...s]));
    }
    function hideBadge(card) {
      const b = card.querySelector('.badge-new');
      if (b) b.style.display = 'none';
    }
    const readSet = getReadSet();
    document.querySelectorAll('.card').forEach(card => {
      if (readSet.has(card.dataset.url)) hideBadge(card);
    });
    document.querySelectorAll('.card a').forEach(link => {
      link.addEventListener('click', () => {
        const card = link.closest('.card');
        if (card) { markRead(card.dataset.url); hideBadge(card); }
      });
    });
  </script>
</body>
</html>"""


def _format_published(iso_str: str) -> str:
    """ISO 8601 文字列を JST の「YYYY-MM-DD HH:MM」形式に変換する"""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_str


def generate_html(
    processed: dict[str, list[ProcessedArticle]],
    output_path: str = "docs/index.html",
) -> None:
    """精査済み記事データからindex.htmlを生成し output_path に書き出す。"""
    now_jst = datetime.now(JST)
    updated_str = now_jst.strftime("%Y-%m-%d %H:%M JST")

    panels: dict = {
        "ai": {
            "social":   {"articles": []},
            "press":    {"articles": []},
            "academic": {"articles": []},
        },
        "neuro": {
            "social":   {"articles": []},
            "press":    {"articles": []},
            "research": {
                "embodiment": {"articles": []},
                "psychology": {"articles": []},
            },
        },
        "neuro_ai": {"articles": []},
    }

    # 全記事を flatten してエンリッチ（impact スコア・カテゴリラベル付与）
    all_articles: list[dict] = []
    for articles in processed.values():
        for a in articles:
            enriched = {
                **a,
                "published_jst":  _format_published(a["published"]),
                "impact":         _impact_score(a),
                "category_label": _CATEGORY_LABELS.get(a.get("category", ""), a.get("category", "")),
                "source":         a.get("source") or _extract_source(a["url"]),
            }
            all_articles.append(enriched)

    # Pass 1: AIカテゴリの hot 候補を収集
    hot_candidates = [
        a for a in all_articles
        if a.get("hot") and a.get("category") in _HOT_CATS
    ]
    hot_candidates.sort(key=lambda a: a.get("published", ""), reverse=True)
    hot_articles = hot_candidates[:3]
    hot_url_set = {a["url"] for a in hot_articles}

    # Pass 2: Gemini カテゴリキーでパネルに振り分け（hot は除外）
    for a in all_articles:
        if a["url"] in hot_url_set:
            continue
        mapping = _CAT_MAP.get(a.get("category", ""))
        if not mapping:
            continue
        parent, sub, sub3 = mapping

        if parent == "ai" and sub:
            panels["ai"][sub]["articles"].append(a)
        elif parent == "neuro" and sub == "research" and sub3:
            panels["neuro"]["research"][sub3]["articles"].append(a)
        elif parent == "neuro" and sub:
            panels["neuro"][sub]["articles"].append(a)
        elif parent == "neuro_ai":
            panels["neuro_ai"]["articles"].append(a)

    # パネルごとに上限10件
    for sub in ("social", "press", "academic"):
        panels["ai"][sub]["articles"] = panels["ai"][sub]["articles"][:10]
    for sub in ("social", "press"):
        panels["neuro"][sub]["articles"] = panels["neuro"][sub]["articles"][:10]
    panels["neuro"]["research"]["embodiment"]["articles"] = \
        panels["neuro"]["research"]["embodiment"]["articles"][:10]
    panels["neuro"]["research"]["psychology"]["articles"] = \
        panels["neuro"]["research"]["psychology"]["articles"][:10]
    panels["neuro_ai"]["articles"] = panels["neuro_ai"]["articles"][:10]

    # All タブ用：hot 以外の全記事を日付降順で最大 30 件
    all_non_hot = [a for a in all_articles if a["url"] not in hot_url_set]
    all_non_hot.sort(key=lambda a: a.get("published", ""), reverse=True)
    all_non_hot_articles = all_non_hot[:30]

    env = Environment(loader=BaseLoader())
    tmpl = env.from_string(HTML_TEMPLATE)
    html = tmpl.render(
        updated=updated_str,
        hot_articles=hot_articles,
        all_non_hot_articles=all_non_hot_articles,
        ai=panels["ai"],
        neuro=panels["neuro"],
        neuro_ai=panels["neuro_ai"],
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[generate] Written to {output_path}")
