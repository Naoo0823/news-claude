"""
LM OS 5.0 プロンプト検証スクリプト
3種類のサンプル記事（AI系 / 脳科学系 / 競合業界系）でインサイト品質を検証する
"""

from __future__ import annotations

import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from process import SYSTEM_PROMPT, MODEL

SAMPLE_ARTICLES = [
    {
        "index": 0,
        "lang": "en",
        "category": "AIプロダクト速報",
        "title": "Anthropic launches Claude for Work with real-time tool use and memory",
        "description": (
            "Anthropic today announced Claude for Work, an enterprise platform that combines "
            "real-time web search, code execution, and persistent memory across sessions. "
            "The system allows managers to configure AI agents that can access internal wikis, "
            "draft performance reviews, and schedule 1-on-1 meetings autonomously. Pricing starts "
            "at $25/user/month for teams above 50 seats."
        ),
    },
    {
        "index": 1,
        "lang": "en",
        "category": "脳科学・社会実装",
        "title": "Oxytocin release during team rituals predicts six-month retention, Stanford study finds",
        "description": (
            "A Stanford study of 1,240 employees across 14 companies found that measurable oxytocin "
            "release during onboarding ceremonies, weekly stand-ups, and goal-setting rituals was "
            "the strongest predictor of six-month retention (r=0.71), outperforming salary and role "
            "clarity. Synchronized physiological arousal—not just verbal agreement—distinguished "
            "high-cohesion teams. Researchers propose that ritual design, not ping-pong tables, "
            "is the true lever for belonging."
        ),
    },
    {
        "index": 2,
        "lang": "en",
        "category": "競合プレスリリース",
        "title": "Korn Ferry launches AI-powered succession planning tool integrated with LinkedIn Talent Insights",
        "description": (
            "Korn Ferry announced a new succession planning platform that ingests LinkedIn Talent "
            "Insights data to automatically identify internal successors and benchmark them against "
            "external talent pools. The tool generates 'readiness scores' for each candidate and "
            "delivers development roadmaps. It is now bundled into Korn Ferry's enterprise talent "
            "management suite at no additional cost for existing clients."
        ),
    },
    {
        "index": 3,
        "lang": "en",
        "category": "業界・市場トレンド",
        "title": "SHRM 2026 report: 68% of HR leaders say employee motivation gap is top barrier to productivity",
        "description": (
            "The Society for Human Resource Management's 2026 State of the Workplace report found "
            "that 68% of HR leaders identify the 'motivation gap'—employees who show up but are "
            "not energized—as the #1 barrier to productivity, ahead of skills shortages (54%) and "
            "hybrid work friction (47%). Only 12% of respondents say their current engagement "
            "platforms give them actionable data on intrinsic motivation drivers. Companies "
            "reporting above-median engagement scores showed 2.3x higher revenue per employee."
        ),
    },
]

USER_PROMPT = (
    "以下の記事リストを分析し、JSON配列のみを返してください。\n\n"
    + json.dumps(SAMPLE_ARTICLES, ensure_ascii=False, indent=2)
)


def run_validation() -> None:
    client = anthropic.Anthropic()

    print("=== LM OS 5.0 プロンプト検証 ===\n")
    print(f"モデル: {MODEL}")
    print(f"サンプル記事数: {len(SAMPLE_ARTICLES)}\n")
    print("APIコール中...\n")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": USER_PROMPT}],
    )

    raw = response.content[0].text.strip()

    # JSON パース
    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        # コードブロックを除去して再試行
        import re
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        results = json.loads(cleaned)

    print(f"{'='*70}\n")
    for r in results:
        idx = r.get("index", "?")
        orig = next((a for a in SAMPLE_ARTICLES if a["index"] == idx), {})
        print(f"[記事 {idx}] {orig.get('category', '')} ({orig.get('lang', '')})")
        print(f"  原題  : {orig.get('title', '')[:60]}...")
        print(f"  訳題  : {r.get('title_ja', '')}")
        print(f"  判定  : selected={r.get('selected')}  hot={r.get('hot')}  impact={r.get('impact')}  category={r.get('category')}")
        print(f"  要約  : {r.get('summary', '')}")
        print(f"  洞察  : {r.get('insight', '')}")
        axes = r.get('impact_axes') or {}
        per = axes.get('per', '-')
        sci = axes.get('sci', '-')
        cps = axes.get('cps', '-')
        print(f"  3軸   : PER={per}  SCI={sci}  CPS={cps}  → impact={r.get('impact')}")
        print(f"  タグ  : {' '.join(r.get('hashtags', []))}")
        print()

    # LM用語チェック
    lm_terms = [
        "Center-pin", "Sense Making", "Unfreeze", "Confidence", "Commit",
        "Corporate-identity", "PCマトリクス", "モチベーションエンジニアリング",
        "ICE BLOCK", "INK BLOT", "農耕型", "狩猟型", "EPS", "PER", "i-Company",
        "4C", "C1", "C2", "C3", "C4",
    ]
    all_text = " ".join([
        r.get("summary", "") + r.get("insight", "")
        for r in results if r.get("selected")
    ])
    found = [t for t in lm_terms if t in all_text]
    missing = [t for t in lm_terms if t not in all_text]

    print(f"{'='*70}")
    print(f"【LM OS 5.0 用語チェック】")
    print(f"  使用済み ({len(found)}): {', '.join(found)}")
    print(f"  未使用   ({len(missing)}): {', '.join(missing)}")
    print()

    # 使用トークン
    usage = response.usage
    print(f"【トークン使用量】")
    print(f"  入力: {usage.input_tokens}  出力: {usage.output_tokens}")
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_create = getattr(usage, "cache_creation_input_tokens", 0)
    if cache_read or cache_create:
        print(f"  キャッシュ読込: {cache_read}  キャッシュ作成: {cache_create}")


if __name__ == "__main__":
    run_validation()
