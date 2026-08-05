"""主入口 — 编排完整监控流水线"""

import logging
import sys

from .config import load_config
from .fetcher import fetch_all_offices, save_snapshot, load_previous_snapshot
from .differ import diff_snapshots, update_timeline
from .notifier import send_notifications


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def run():
    """主流水线"""
    setup_logging()
    logger = logging.getLogger("quota_monitor.run")
    logger.info("=" * 50)
    logger.info("HKID Quota Monitor 启动")

    # 1. 加载配置
    config = load_config()
    logger.info(f"监控窗口: {config['monitor']['monitor_before']}")
    logger.info(f"紧急线:   {config['monitor']['urgent_before']}")
    logger.info(f"提醒线:   {config['monitor']['notice_before']}")

    # 2. 加载上一轮快照
    logger.info("--- 第 1 步: 加载历史快照 ---")
    previous = load_previous_snapshot()
    if previous:
        prev_time = previous.get("fetched_at", "未知")
        logger.info(f"历史快照时间: {prev_time}")
    else:
        logger.info("无历史快照（首次运行）")

    # 3. 抓取最新数据
    logger.info("--- 第 2 步: 抓取配额数据 ---")
    current = fetch_all_offices()

    # 4. 保存快照
    logger.info("--- 第 3 步: 保存快照 ---")
    save_snapshot(current)

    # 5. Diff 比对
    logger.info("--- 第 4 步: Diff 比对 ---")
    events = diff_snapshots(previous, current, config)
    if events:
        for e in events:
            icon = {"urgent": "🚨", "notice": "🔔", "regular": "📋"}.get(e["level"], "")
            logger.info(f"  {icon} {e['name_zh']} — {e['date']} ({e['new_quota']} 个名额) [{e['level']}]")
    else:
        logger.info("无新的放号事件")

    # 6. 更新时间线
    logger.info("--- 第 5 步: 更新时间线 ---")
    if events:
        update_timeline(events)

    # 7. 发送通知
    logger.info("--- 第 6 步: 发送通知 ---")
    if events:
        send_notifications(events, config)

    logger.info("=" * 50)
    logger.info("完成")

    return current, events


if __name__ == "__main__":
    run()
