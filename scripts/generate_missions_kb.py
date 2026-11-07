"""Build the mission guide catalog from the GTA Wiki MediaWiki API.

The source wiki is CC BY-SA. Keep page-level attribution in every record and
retain the repository-level notice when redistributing the generated catalog.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data_kb" / "missions_kb.json"
API = "https://gta.fandom.com/api.php"
MAIN_PAGE = "Missions in GTA V"
SIDE_PAGE = "Strangers and Freaks"
USER_AGENT = "GTA-AI-Copilot-KB/1.0 (mission data research)"
EXISTING_SCRIPT_IDS = {
    "Franklin and Lamar": "armenian1",
    "Fame or Shame": "family4",
    "The Jewel Store Job": "jewelry_heist",
    "Mr. Philips": "trevor1",
    "The Bus Assassination": "assassin_bus",
}
SCRIPT_ALIASES = {
    "Prologue": "prologue1",
    "Franklin and Lamar": "armenian1",
    "Repossession": "armenian2",
    "Complications": "armenian3",
    "Friend Request": "lester1",
    "Casing the Jewel Store": "jewelry_setup1",
    "The Jewel Store Job": "jewelry_heist",
    "Mr. Philips": "trevor1",
    "Fame or Shame": "family4",
    "The Hotel Assassination": "assassin_valet",
}


def fetch_wikitext(page: str) -> str:
    query = urllib.parse.urlencode({
        "action": "parse", "page": page, "prop": "wikitext", "format": "json",
    })
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
            return payload["parse"]["wikitext"]["*"].replace("\ufffdC", "–")
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def wiki_links(text: str) -> list[tuple[str, str]]:
    result = []
    for target, label in re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", text):
        if target.lower().startswith(("file:", "category:", "wikipedia:")):
            continue
        target = target.split("#", 1)[0].strip()
        display = plain_text(label).strip() if label else target
        display = re.sub(r"''+", "", display).strip()
        if target and display:
            result.append((target, display))
    return result


def plain_text(markup: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", markup, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[(?:https?://\S+\s+)?([^\]]+)\]", r"\1", text)
    text = re.sub(r"</?(?:small|br|div|span|p|ref|nowiki|center|blockquote)[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"<ref[^>]*/>", " ", text, flags=re.I)
    text = re.sub(r"'{2,5}", "", text)
    text = re.sub(r"\[\[File:[^\]]+\]\]", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" |\t\r\n")


def table_missions(section: str, kind: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in re.split(r"(?m)^\|-", section):
        if not re.search(r"\[\[", row):
            continue
        cells = re.split(r"(?m)^\|", row)
        if len(cells) < 2:
            continue
        title_cell = cells[1]
        links = wiki_links(title_cell)
        if not links:
            continue
        target, title = links[-1]
        if title.lower() in {"title", "description", "rewards"}:
            continue
        description = plain_text(cells[2]) if len(cells) > 2 else ""
        if title not in {item["title_en"] for item in records}:
            records.append({"wiki_title": target, "title_en": title, "description": description, "kind": kind})
    return records


def mission_catalog() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    text = fetch_wikitext(MAIN_PAGE)
    start = text.index("==Main Story Missions==")
    stop = text.index("==Side Missions==", start)
    story = table_missions(text[start:stop], "story")

    side_text = fetch_wikitext(SIDE_PAGE)
    strangers = table_missions(side_text, "strangers_and_freaks")
    headings = {
        plain_text(value).casefold()
        for value in re.findall(r"(?m)^==([^=]+)==\s*$", side_text)
    }
    strangers = [item for item in strangers if item["title_en"].casefold() not in headings]

    side_start = text.index("==Side Missions==")
    side_end = text.index("==Trivia==", side_start)
    side = table_missions(text[side_start:side_end], "side") + strangers
    story_titles = {item["title_en"].casefold() for item in story}
    seen = set(story_titles)
    deduplicated = []
    for item in side:
        normalized = item["title_en"].casefold()
        if normalized not in seen:
            deduplicated.append(item)
            seen.add(normalized)
    side = deduplicated
    return story, side


def section_text(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^=={re.escape(heading)}==\s*$", text)
    if not match:
        return ""
    next_heading = re.search(r"(?m)^==[^=].*?==\s*$", text[match.end():])
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end():end].strip()


def extract_bullets(section: str) -> list[str]:
    values = []
    for line in section.splitlines():
        if re.match(r"^\s*[#*;]", line):
            value = plain_text(re.sub(r"^\s*[#*;]+\s*", "", line))
            if value and value not in values:
                values.append(value)
    if not values:
        rows = re.split(r"(?m)^\|-", section)
        for row in rows:
            if "|" in row:
                value = plain_text(row)
                if value and value not in values:
                    values.append(value)
    return values


def extract_walkthrough(section: str) -> list[str]:
    if not section:
        return []
    objectives = list(re.finditer(r"(?m)^:\{\{anchor\|[^}]+\}\}'''(.*?)'''\s*$", section))
    if objectives:
        result = []
        for index, match in enumerate(objectives):
            end = objectives[index + 1].start() if index + 1 < len(objectives) else len(section)
            heading = plain_text(match.group(1))
            body = section[match.end():end]
            paragraphs = []
            for chunk in re.split(r"\n\s*\n", body):
                value = plain_text(chunk)
                if value and not value.startswith(("{{", "===", "[[File:")):
                    paragraphs.append(value)
            result.append(" ".join([heading, *paragraphs]))
        return result
    return extract_bullets(section)


def extract_gold_medals(section: str) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    for line in section.splitlines():
        first = re.match(r"^\*([^*].*)$", line.strip())
        nested = re.match(r"^\*{2,}\s*(.*)$", line.strip())
        if first:
            condition = plain_text(first.group(1))
            if condition:
                name, separator, detail = condition.partition(" - ")
                requirements.append({"name": name.strip(), "condition": condition, "tip": ""})
        elif nested and requirements:
            tip = plain_text(nested.group(1))
            if tip:
                requirements[-1]["tip"] = (requirements[-1]["tip"] + " " + tip).strip()
    if requirements:
        return requirements
    return [{"name": value.split(":", 1)[0], "condition": value, "tip": ""}
            for value in extract_bullets(section)]


def script_id_for(item: dict[str, str]) -> str | None:
    title = item["title_en"]
    if title in EXISTING_SCRIPT_IDS:
        return EXISTING_SCRIPT_IDS[title]
    if title in SCRIPT_ALIASES:
        return SCRIPT_ALIASES[title]
    return None


def catalog_key_for(item: dict[str, str]) -> str:
    verified_id = script_id_for(item)
    if verified_id:
        return verified_id
    slug = re.sub(r"[^a-z0-9]+", "_", item["title_en"].lower()).strip("_")
    return slug or "wiki_unknown"


def preserve_curated_fields(key: str, record: dict[str, Any], old_record: dict[str, Any] | None = None) -> None:
    old_record = old_record or {}
    old_translation = old_record.get("title_zh") or (
        old_record.get("name") if old_record.get("name") != old_record.get("title_en") else None
    )
    if old_translation:
        record["title_zh"] = old_translation
    for field in ("key_tips", "stock_guide"):
        if old_record.get(field):
            record[field] = old_record[field]
    if key == "assassin_bus":
        if not record.get("title_zh") or record.get("title_zh") == record.get("title_en"):
            record["title_zh"] = "巴士暗杀 / The Bus Assassination"
        if not record.get("stock_guide"):
            record["stock_guide"] = [
            {"timing": "任务前", "action": "不要为本任务提前买入 Vapid（VAP）股票。"},
            {"timing": "任务后", "action": "任务完成后观察 Vapid 股价下跌，在低位分批买入；等待价格回升后卖出。"},
            {"timing": "风险提示", "action": "股价与回升幅度会受游戏版本、存档进度及等待时间影响；先手动存档并观察市场，不保证固定收益。"},
            ]
        if not record.get("key_tips"):
            record["key_tips"] = [
                "巴士暗杀的常见投资时机是任务后买入 Vapid，勿与其他莱斯特暗杀任务混淆。",
                "金牌条件以游戏内任务清单为准。",
            ]


def apply_schema_contract(record: dict[str, Any]) -> None:
    record["gold_medal_criteria"] = record.get("gold_medal_requirements", [])
    guide_status = record.get("guide_status", "catalog_only")
    has_steps = bool(record.get("steps"))
    has_gold = bool(record.get("gold_medal_criteria"))
    record["data_completeness"] = {
        "steps": "sourced" if has_steps else "missing_source_detail",
        "gold_medal_criteria": "sourced" if has_gold else "not_listed_on_source",
        "gold_medal_applicability": "listed" if has_gold else "unknown_from_source",
        "tips": "sourced" if record.get("key_tips") else "not_compiled",
        "summary_status": guide_status,
    }


def fetch_mission_record(item: dict[str, str]) -> dict[str, Any]:
    try:
        text = fetch_wikitext(item["wiki_title"])
    except Exception as exc:  # Keep the catalog complete even if one page is unavailable.
        return {
            **item, "script_id": script_id_for(item), "catalog_key": catalog_key_for(item), "guide_status": "catalog_only",
            "walkthrough": [], "gold_medal_requirements": [], "source_error": str(exc),
        }

    walkthrough = extract_walkthrough(section_text(text, "Walkthrough"))
    if not walkthrough:
        walkthrough = extract_bullets(section_text(text, "Mission Objectives"))
    gold = extract_gold_medals(section_text(text, "Gold Medal Objectives"))
    if walkthrough and gold:
        guide_status = "walkthrough_and_gold"
    elif walkthrough:
        guide_status = "walkthrough_only"
    elif gold:
        guide_status = "gold_only"
    else:
        guide_status = "catalog_only"
    return {
        "script_id": script_id_for(item),
        "catalog_key": catalog_key_for(item),
        "kind": item["kind"],
        "mission_number": None,
        "name": item["title_en"],
        "title_zh": None,
        "title_en": item["title_en"],
        "characters": [],
        "description": item["description"],
        "steps": [{"stage": n, "title": f"Stage {n}", "action": text} for n, text in enumerate(walkthrough, 1)],
        "walkthrough": walkthrough,
        "gold_medal_requirements": gold,
        "key_tips": [],
        "guide_status": guide_status,
        "source": {
            "title": item["wiki_title"],
            "url": "https://gta.fandom.com/wiki/" + urllib.parse.quote(item["wiki_title"].replace(" ", "_")),
            "license": "CC BY-SA",
        },
    }


def build(output: Path = KB_PATH, workers: int = 5) -> dict[str, Any]:
    story, side = mission_catalog()
    current = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    old = current.get("missions", {})
    records = story + side

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        fetched = list(executor.map(fetch_mission_record, records))

    missions: dict[str, Any] = {}
    story_order = {item["title_en"]: number for number, item in enumerate(story, 1)}
    for record in fetched:
        key = record["catalog_key"]
        old_record = old.get(key, {})
        if record.get("kind") == "story":
            record["mission_number"] = story_order[record["title_en"]]
        preserve_curated_fields(key, record, old_record)
        apply_schema_contract(record)
        missions[key] = record

    for key, old_record in old.items():
        if key in set(EXISTING_SCRIPT_IDS.values()):
            missions.setdefault(key, old_record)

    result = {
        "schema_version": 2,
        "language": "zh-CN",
        "content_language": "en",
        "mission_order_basis": "GTA Wiki directory row order; not chronological or required playthrough order",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_counts": {
            "story_missions": len(story),
            "side_missions": len(side),
            "strangers_and_freaks": sum(item["kind"] == "strangers_and_freaks" for item in side),
        },
        "missions": missions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--output", type=Path, default=KB_PATH)
    parser.add_argument("--dedupe-cached", action="store_true", help="Remove duplicate titles from the current generated catalog without fetching pages")
    args = parser.parse_args()
    if args.dedupe_cached:
        current = json.loads(args.output.read_text(encoding="utf-8"))
        catalog = current.get("missions", {})
        grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for key, record in catalog.items():
            title = str(record.get("title_en") or record.get("name") or key).casefold()
            grouped.setdefault(title, []).append((key, record))
        compact: dict[str, Any] = {}
        for values in grouped.values():
            key, record = next(((key, record) for key, record in values if key == record.get("catalog_key")), values[0])
            preserve_curated_fields(key, record)
            apply_schema_contract(record)
            compact[key] = record
        current["missions"] = compact
        args.output.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Deduplicated catalog: {len(catalog)} -> {len(compact)} records")
        return 0
    result = build(args.output, max(1, min(args.workers, 10)))
    print(json.dumps({"story_missions": result["source_counts"]["story_missions"],
                      "strangers_and_freaks": result["source_counts"]["strangers_and_freaks"],
                      "total": len(result["missions"]),
                      "sourced_guides": sum(m["guide_status"] != "catalog_only" for m in result["missions"].values())}, indent=2))
    if result["source_counts"]["story_missions"] != 69:
        print("WARNING: story mission count differs from expected 69", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
