"""Diff 比对：检测放号事件"""

import logging
from datetime import datetime, timezone, timedelta

from .config import get_alert_level

logger = logging.getLogger(__name__)

HKT = timezone(timedelta(hours=8))


def diff_snapshots(previous: dict, current: dict, config: dict) -> list:
    """
    比较两轮快照，返回放号事件列表。

    返回:
    [
        {
            "office": "WC",
            "name_zh": "湾仔",
            "date": "2026-08-10",
            "old_quota": 0,
            "new_quota": 5,
            "level": "urgent" | "notice" | "regular",
            "time": "2026-08-05T14:30:00+08:00"
        },
        ...
    ]
    """
    events = []
    prev_offices = previous.get("offices", {})
    curr_offices = current.get("offices", {})

    for office_id, curr_data in curr_offices.items():
        prev_data = prev_offices.get(office_id, {})
        prev_quota = prev_data.get("quota", {})
        curr_quota = curr_data.get("quota", {})

        if "error" in curr_data:
            continue  # 抓取失败的办事处跳过

        for date_str, new_q in curr_quota.items():
            old_q = prev_quota.get(date_str, -1)

            # 只检测 0→正数 或 正数→更多 的变化
            if old_q < new_q and new_q > 0:
                level = get_alert_level(date_str, config)
                if level == "ignore":
                    continue

                events.append({
                    "office": office_id,
                    "name_zh": curr_data.get("name_zh", office_id),
                    "date": date_str,
                    "old_quota": old_q if old_q >= 0 else 0,
                    "new_quota": new_q,
                    "level": level,
                    "time": current.get("fetched_at", datetime.now(HKT).isoformat()),
                })

    # 按紧急程度和日期排序
    level_order = {"urgent": 0, "notice": 1, "regular": 2}
    events.sort(key=lambda e: (level_order.get(e["level"], 3), e["date"]))

    logger.info(f"检测到 {len(events)} 个放号事件")
    return events


def update_timeline(events: list):
    """将新的放号事件追加到 data/timeline.json"""
    import json
    from .config import ROOT

    timeline_path = ROOT / "data" / "timeline.json"

    existing = {"events": []}
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # 去重：同一办事处+同一天 在 1 小时内不重复添加
    now = datetime.now(HKT)
    seen = set()
    for evt in existing.get("events", []):
        try:
            evt_time = datetime.fromisoformat(evt["time"])
            if (now - evt_time).total_seconds() < 3600:
                seen.add((evt["office"], evt["date"]))
        except (KeyError, ValueError):
            pass

    new_events = [e for e in events if (e["office"], e["date"]) not in seen]
    existing["events"] = new_events + existing.get("events", [])

    # 保留最近 200 条
    existing["events"] = existing["events"][:200]

    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"时间线已更新: {len(new_events)} 条新记录")
