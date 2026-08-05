"""Diff 比对：检测放号事件（基于状态变化 r→g/y→g）"""

import json
import logging
from datetime import datetime, timezone, timedelta

from .config import get_alert_level, ROOT

logger = logging.getLogger(__name__)

HKT = timezone(timedelta(hours=8))

# 状态可预约性: g > y > r, x = 不可用
STATUS_AVAILABLE = {"g": 3, "y": 2, "r": 1, "x": 0, "?": 0}


def diff_snapshots(previous: dict, current: dict, config: dict) -> list:
    """
    比较两轮快照，当配额从"已满(r)"变为"充足(g)/少量(y)"时视为放号。

    返回:
    [
        {
            "office": "RHK",
            "name_zh": "湾仔",
            "date": "2026-08-10",
            "old_status": "r",
            "new_status": "g",
            "session": "R",
            "level": "urgent" | "notice" | "regular",
            "time": "2026-08-05T14:30:00+08:00"
        },
        ...
    ]
    """
    events = []
    prev_offices = previous.get("offices", {})
    curr_offices = current.get("offices", {})

    if not prev_offices:
        logger.info("跳过 diff — 无历史快照")
        return events

    for office_id, curr_data in curr_offices.items():
        prev_data = prev_offices.get(office_id, {})
        prev_quota = prev_data.get("quota", {})
        curr_quota = curr_data.get("quota", {})

        if not prev_quota:
            # 首次获取到该办事处数据，不视为放号
            continue

        for date_str, curr_statuses in curr_quota.items():
            prev_statuses = prev_quota.get(date_str, {})

            for session in ("R", "K"):
                old_s = prev_statuses.get(session, "?") if prev_statuses else "?"
                new_s = curr_statuses.get(session, "?")

                # 检测状态改善: 从不可约(r/x) → 可约(g/y)，或从少量(y) → 充足(g)
                old_val = STATUS_AVAILABLE.get(old_s, 0)
                new_val = STATUS_AVAILABLE.get(new_s, 0)

                # 只有状态变好了才算放号
                if new_val > old_val and new_val >= 2:  # 至少变成 "少量" 或以上
                    # 跳过首次出现（old_s 为 ? 表示历史没记录）
                    if old_val == 0 and old_s != "r" and old_s != "x":
                        continue

                    level = get_alert_level(date_str, config)
                    if level == "ignore":
                        continue

                    session_label = "一般" if session == "R" else "延长"
                    events.append({
                        "office": office_id,
                        "name_zh": curr_data.get("name_zh", office_id),
                        "date": date_str,
                        "old_status": old_s,
                        "new_status": new_s,
                        "session": session,
                        "session_label": session_label,
                        "level": level,
                        "time": current.get("fetched_at", datetime.now(HKT).isoformat()),
                    })

    # 按紧急程度和日期排序
    level_order = {"urgent": 0, "notice": 1, "regular": 2}
    events.sort(key=lambda e: (level_order.get(e["level"], 3), e["date"]))

    if events:
        for e in events:
            icon = {"urgent": "🚨", "notice": "🔔", "regular": "📋"}.get(e["level"], "")
            logger.info(
                f"  {icon} {e['name_zh']} {e['date']} [{e['session_label']}时段] "
                f"{e['old_status']}→{e['new_status']} [{e['level']}]"
            )
    else:
        logger.info("无新的放号事件")

    return events


def update_timeline(events: list):
    """将新的放号事件追加到 data/timeline.json"""
    timeline_path = ROOT / "data" / "timeline.json"

    existing = {"events": []}
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # 去重：同一办事处+日期+时段 2 小时内不重复
    now = datetime.now(HKT)
    seen = set()
    for evt in existing.get("events", []):
        try:
            evt_time = datetime.fromisoformat(evt["time"])
            if (now - evt_time).total_seconds() < 7200:
                key = (evt.get("office"), evt.get("date"), evt.get("session"))
                seen.add(key)
        except (KeyError, ValueError):
            pass

    new_events = []
    for e in events:
        key = (e["office"], e["date"], e["session"])
        if key not in seen:
            new_events.append(e)
            seen.add(key)

    existing["events"] = new_events + existing.get("events", [])

    # 保留最近 200 条
    existing["events"] = existing["events"][:200]

    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"时间线已更新: {len(new_events)} 条新记录")
