"""乃木坂46公式サイトの今日のスケジュールを Discord(Webhook)に通知する。

公式サイトは、予定をページを開いたあとに読み込む作りのため、
Playwright(ブラウザ)で実際にページを開いてから読み取る。

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
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://www.nogizaka46.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
JST = ZoneInfo("Asia/Tokyo")
LINK = 'a[href*="/media/detail/"]'

# ページ内の予定リンクを全部集め、「TODAY'S SCHEDULE」欄の中のものも別に集める
JS = r"""
() => {
  const pick = (root) => [...root.querySelectorAll('a[href*="/media/detail/"]')]
      .map(a => ({href: a.href, text: a.innerText || a.textContent || ''}));
  const all = pick(document);
  const leaf = [...document.querySelectorAll('*')].find(
      e => e.children.length === 0 && /TODAY.{0,2}S\s*SCHEDULE/i.test(e.textContent || ''));
  let section = [];
  if (leaf) {
    let el = leaf.parentElement;
    while (el && el.querySelectorAll('a[href*="/media/detail/"]').length === 0) {
      el = el.parentElement;
    }
    if (el) section = pick(el);
  }
  return {all, section};
}
"""


class ScrapeError(RuntimeError):
    pass


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # 「14:00〜14:45 14:00〜14:45」のような時間の重複を1つにする
    return re.sub(r"(\d{1,2}:\d{2}(?:[〜～~](?:\d{1,2}:\d{2})?)?)\s*\1", r"\1", text)


def ymd(href: str):
    q = parse_qs(urlparse(href).query)
    try:
        return int(q["wd00"][0]), int(q["wd01"][0]), int(q["wd02"][0])
    except (KeyError, ValueError):
        return None


def render(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector(LINK, timeout=20000)  # 予定が読み込まれるのを待つ
    except PWTimeout:
        print(f"WARN: {url} で予定リンクが現れませんでした", file=sys.stderr)
    page.wait_for_timeout(1500)
    return page.evaluate(JS)


def collect(today: datetime) -> list[dict]:
    key_today = (today.year, today.month, today.day)
    pages = [
        ("top", f"{BASE}/s/n46/?ima=3440"),
        ("list", f"{BASE}/s/n46/media/list?ima=3440&dy={today:%Y%m}"),
    ]
    items: dict[str, dict] = {}
    seen_total = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA, locale="ja-JP", timezone_id="Asia/Tokyo",
                                  viewport={"width": 1280, "height": 1600})
        page = ctx.new_page()
        for name, url in pages:
            try:
                data = render(page, url)
            except Exception as e:
                print(f"WARN: {name} の取得に失敗: {e}", file=sys.stderr)
                continue
            all_a, section = data["all"], data["section"]
            seen_total += len(all_a)
            print(f"[{name}] 予定リンク {len(all_a)}件 / TODAY欄 {len(section)}件")

            # 1) TODAY'S SCHEDULE 欄の中のもの(日付が付いていて今日と違うものは除く)
            # 2) どのリンクでも、日付が今日のもの
            cands = [a for a in section if ymd(a["href"]) in (None, key_today)]
            cands += [a for a in all_a if ymd(a["href"]) == key_today]
            for a in cands:
                key = a["href"].split("?")[0]
                text = clean(a["text"])
                if text and key not in items:
                    items[key] = {"url": key, "text": text}
        browser.close()

    print(f"今日の予定: {len(items)}件")
    if seen_total == 0:
        raise ScrapeError("ページから予定リンクを1つも読み取れませんでした")

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
    wd = "月火水木金土日"[today.weekday()]
    header = f"📅 **乃木坂46 TODAY'S SCHEDULE** {today:%Y/%m/%d}({wd})"

    try:
        items = collect(today)
    except ScrapeError as e:
        # 「予定なし」と間違えないよう、取得失敗をはっきり知らせる
        send_discord(webhook, f"{header}\n⚠️ 予定を取得できませんでした({e})。サイトの作りが変わった可能性があります。")
        raise

    members = [m.strip() for m in os.environ.get("MEMBERS", "").split(",") if m.strip()]
    if members:
        items = [it for it in items if any(m in it["text"] for m in members)]

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
