"""邮件通知模块 — 通过 QQ SMTP 发送放号提醒"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

from .config import ROOT

logger = logging.getLogger(__name__)

HKT = timezone(timedelta(hours=8))

# 邮件模板
URGENT_SUBJECT = "🚨 [紧急] HKID 预约名额释放 — {office} {date}"
NOTICE_SUBJECT = "🔔 [提醒] HKID 预约名额释放 — {office} {date}"
REGULAR_SUBJECT = "📋 HKID 预约名额更新 — {office} {date}"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-HK">
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, 'PingFang HK', sans-serif; background:#f1f5f9; padding:20px;">
<div style="max-width:520px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px rgba(0,0,0,0.1);">

  <!-- 标题栏 -->
  <div style="background:{color}; padding:18px 24px; text-align:center;">
    <h2 style="color:#fff; margin:0; font-size:18px;">{level_icon} {level_label}</h2>
    <p style="color:rgba(255,255,255,0.85); margin:6px 0 0; font-size:13px;">香港身份证预约配额监控</p>
  </div>

  <!-- 内容 -->
  <div style="padding:24px;">
    <table style="width:100%; border-collapse:collapse; font-size:14px;">
      <tr>
        <td style="padding:10px 12px; color:#64748b; border-bottom:1px solid #e2e8f0;">📍 办事处</td>
        <td style="padding:10px 12px; font-weight:600; border-bottom:1px solid #e2e8f0;">{office}（{office_en}）</td>
      </tr>
      <tr>
        <td style="padding:10px 12px; color:#64748b; border-bottom:1px solid #e2e8f0;">📅 可预约日期</td>
        <td style="padding:10px 12px; font-weight:600; color:{color}; border-bottom:1px solid #e2e8f0;">{dates}</td>
      </tr>
      <tr>
        <td style="padding:10px 12px; color:#64748b;">⏰ 检测时间</td>
        <td style="padding:10px 12px;">{time}</td>
      </tr>
    </table>

    <div style="margin-top:24px; text-align:center;">
      <a href="https://www.gov.hk/sc/apps/immdicbooking2.htm"
         style="display:inline-block; padding:12px 32px; background:{color}; color:#fff;
                text-decoration:none; border-radius:8px; font-size:15px; font-weight:600;">
        立即前往预约 →
      </a>
    </div>

    <p style="margin-top:20px; font-size:12px; color:#94a3b8; text-align:center;">
      ⚠️ 此邮件由第三方监控工具自动发送，非入境处官方通知<br>
      名额随时可能被约满，请尽快行动
    </p>
  </div>

  <div style="padding:14px; background:#f8fafc; text-align:center; font-size:11px; color:#94a3b8;">
    HKID Quota Monitor · 第三方公益工具
  </div>

</div>
</body>
</html>"""


def get_email_config(config: dict) -> dict:
    """从 Secrets 和环境变量读取邮件配置"""
    email_cfg = config.get("notification", {}).get("email", {})

    return {
        "enabled": email_cfg.get("enabled", True),
        "smtp_host": email_cfg.get("smtp_host", "smtp.qq.com"),
        "smtp_port": email_cfg.get("smtp_port", 587),
        "user": os.environ.get("QQ_SMTP_USER", ""),
        "password": os.environ.get("QQ_SMTP_PASS", ""),
        "admin_email": os.environ.get("ADMIN_EMAIL", ""),
        "subject_prefix": email_cfg.get("subject_prefix", "[HKID预约监控]"),
        "daily_limit": email_cfg.get("daily_limit", 300),
    }


def send_notifications(events: list, config: dict):
    """发送邮件通知（合并同一批次的所有事件为一封邮件）"""
    email_cfg = get_email_config(config)

    if not email_cfg["enabled"]:
        logger.info("邮件通知已禁用")
        return

    if not events:
        logger.info("无放号事件，跳过通知")
        return

    if not email_cfg["user"] or not email_cfg["password"]:
        logger.warning("SMTP 凭据未配置，跳过邮件发送")
        return

    recipient = email_cfg["admin_email"]
    if not recipient:
        logger.warning("ADMIN_EMAIL 未配置，跳过邮件发送")
        return

    # 构建邮件
    highest_level = _get_highest_level(events)
    subject, html_body = _build_email(events, highest_level, config)

    try:
        _send_email(email_cfg, recipient, subject, html_body)
        logger.info(f"邮件已发送至 {recipient}: {subject}")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")


def _get_highest_level(events: list) -> str:
    """返回最高提醒级别"""
    if any(e["level"] == "urgent" for e in events):
        return "urgent"
    if any(e["level"] == "notice" for e in events):
        return "notice"
    return "regular"


def _build_email(events: list, level: str, config: dict) -> tuple:
    """构建邮件主题和 HTML 正文"""
    level_info = config.get("notification", {}).get("levels", {}).get(level, {})
    color = level_info.get("color", "#3b82f6")
    level_label = level_info.get("label", "名额更新")
    level_icon = {"urgent": "🚨", "notice": "🔔", "regular": "📋"}.get(level, "📋")

    # 主题
    office_names = list({e["name_zh"] for e in events})
    if len(events) == 1:
        e = events[0]
        subject = f"{level_icon} HKID 放号 — {e['name_zh']} {e['date']}"
    else:
        subject = f"{level_icon} HKID 放号 — {', '.join(office_names[:3])}"
        if len(office_names) > 3:
            subject += f" 等 {len(office_names)} 处"

    if level == "urgent":
        subject = "🚨 [紧急] " + subject.replace("🚨 ", "")

    # 正文：构建事件表格行
    event_rows = ""
    for e in events:
        event_rows += f"""
        <tr>
          <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0;">
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%;
                         background:{_level_color(e['level'], config)}; margin-right:6px;"></span>
            {e['name_zh']}
          </td>
          <td style="padding:8px 12px; font-weight:600; border-bottom:1px solid #e2e8f0;">{e['date']}</td>
          <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; color:{color}; font-weight:600;">
            {e['new_quota']} 个名额
          </td>
        </tr>"""

    now_str = datetime.now(HKT).strftime("%Y-%m-%d %H:%M:%S")

    html_body = f"""<!DOCTYPE html>
<html lang="zh-HK">
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, 'PingFang HK', sans-serif; background:#f1f5f9; padding:20px;">
<div style="max-width:560px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px rgba(0,0,0,0.1);">

  <div style="background:{color}; padding:18px 24px; text-align:center;">
    <h2 style="color:#fff; margin:0; font-size:18px;">{level_icon} {level_label}</h2>
    <p style="color:rgba(255,255,255,0.85); margin:6px 0 0; font-size:13px;">
      检测到 {len(events)} 个办事处有新名额释放
    </p>
  </div>

  <div style="padding:24px;">
    <table style="width:100%; border-collapse:collapse; font-size:14px;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="padding:8px 12px; text-align:left; color:#64748b; font-size:12px;">办事处</th>
          <th style="padding:8px 12px; text-align:left; color:#64748b; font-size:12px;">可约日期</th>
          <th style="padding:8px 12px; text-align:left; color:#64748b; font-size:12px;">名额</th>
        </tr>
      </thead>
      <tbody>{event_rows}</tbody>
    </table>

    <div style="margin-top:24px; text-align:center;">
      <a href="https://www.gov.hk/sc/apps/immdicbooking2.htm"
         style="display:inline-block; padding:12px 32px; background:{color}; color:#fff;
                text-decoration:none; border-radius:8px; font-size:15px; font-weight:600;">
        立即前往预约 →
      </a>
    </div>

    <p style="margin-top:20px; font-size:12px; color:#94a3b8; text-align:center;">
      ⚠️ 第三方监控工具自动发送，非入境处官方通知<br>
      名额随时可能被约满，请尽快行动 · {now_str}
    </p>
  </div>

  <div style="padding:14px; background:#f8fafc; text-align:center; font-size:11px; color:#94a3b8;">
    HKID Quota Monitor · 第三方公益工具 · 仅做监控提醒
  </div>

</div>
</body>
</html>"""

    return subject, html_body


def _level_color(level: str, config: dict) -> str:
    colors = {"urgent": "#dc2626", "notice": "#f59e0b", "regular": "#3b82f6"}
    return colors.get(level, "#3b82f6")


def _send_email(email_cfg: dict, recipient: str, subject: str, html_body: str):
    """通过 SMTP 发送邮件"""
    msg = MIMEMultipart("alternative")
    msg["From"] = email_cfg["user"]
    msg["To"] = recipient
    msg["Subject"] = subject

    # 纯文本回退
    text = f"HKID 预约名额监控通知\n\n请查看 HTML 邮件获取详情\n预约链接: https://www.gov.hk/sc/apps/immdicbooking2.htm"
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"], timeout=30) as server:
        server.starttls()
        server.login(email_cfg["user"], email_cfg["password"])
        server.sendmail(email_cfg["user"], recipient, msg.as_string())
