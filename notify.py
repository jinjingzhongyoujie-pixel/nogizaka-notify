"""乃木坂46公式サイトの今日のスケジュールを Discord(Webhook)に通知する。

環境変数:
  DISCORD_WEBHOOK_URL  (必須) 通知先チャンネルのWebhook URL
  MEMBERS              (任意) 通知したいメンバー名。カンマ区切り(例: 賀喜遥香,川﨑桜)
                       未設定なら全員分。名前は公式サイトの表記(スペースなし)で書く
  SEND_EMPTY           (任意) "0" で、予定がない日は通知しない
"""
import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.nogizaka46.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal schedule notifier)"}
JST = ZoneInfo("Asia/Tokyo")


def fetch(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def clean(text: str) -> str:
    # 「14:00〜14:45 14:00〜14:45」のような時間の重複を1つにする
    text = re.sub(r"(\d{1,2}:\d{2}(?:〜(?:\d{1,2}:\d{2})?)?)\s*\1", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def collect(today: datetime) -> list[dict]:
    pages = [
        f"{BASE}/s/n46/?ima=3440",
        f"{BASE}/s/n46/media/list?ima=3440&dy={today:%Y%m}",
    ]
    items: dict[str, dict] = {}
    ok = 0
    for page in pages:
        try:
            soup = fetch(page)
            ok += 1
        except Exception as e:  # 片方が失敗しても続行
            print(f"WARN: {page} の取得に失敗: {e}", file=sys.stderr)
            continue
        for a in soup.select('a[href*="/media/detail/"]'):
            href = urljoin(BASE, a["href"])
            q = parse_qs(urlparse(href).query)
            try:
                y, m, d = int(q["wd00"][0]), int(q["wd01"][0]), int(q["wd02"][0])
            except (KeyError, ValueError):
                continue
            if (y, m, d) != (today.year, today.month, today.day):
                continue
            key = href.split("?")[0]
            text = clean(a.get_text(" ", strip=True))
            if text and key not in items:
                items[key] = {"url": key, "text": text}
    if ok == 0:
        raise RuntimeError("サイトを1ページも取得できませんでした")

    def sort_key(it):
        m = re.search(r"(\d{1,2}):(\d{2})", it["text"])
        return (0, int(m.group(1)), int(m.group(2))) if m else (1, 0, 0)

    return sorted(items.values(), key=sort_key)


def send_discord(webhook: str, content: str) -> None:
    # Discordは1メッセージ2000文字まで。行単位で分割して送る
    chunks, cur = [], ""
    for line in content.split("\n"):
        if len(cur) + len(line) + 1 > 1900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    for c in chunks:
        requests.post(webhook, json={"content": c}, timeout=30).raise_for_status()


def main() -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("DISCORD_WEBHOOK_URL が設定されていません")

    today = datetime.now(JST)
    items = collect(today)

    members = [m.strip() for m in os.environ.get("MEMBERS", "").split(",") if m.strip()]
    if members:
        items = [it for it in items if any(m in it["text"] for m in members)]

    wd = "月火水木金土日"[today.weekday()]
    header = f"📅 **乃木坂46 TODAY'S SCHEDULE** {today:%Y/%m/%d}({wd})"

    if not items:
        if os.environ.get("SEND_EMPTY", "1") == "0":
            print("予定なし。通知しません")
            return
        send_discord(webhook, f"{header}\n今日の予定は見つかりませんでした。")
        return

    lines = [header, ""]
    for it in items:
        lines.append(f"・{it['text']}\n  <{it['url']}>")
    send_discord(webhook, "\n".join(lines))
    print(f"{len(items)}件を通知しました")


if __name__ == "__main__":
    main()
