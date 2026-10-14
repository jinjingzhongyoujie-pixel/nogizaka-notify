"""写真ボタンを専用チャンネルに設置する(最初に1回だけ実行)。

環境変数:
  DISCORD_BOT_TOKEN          Botのトークン
  DISCORD_BUTTON_CHANNEL_ID  ボタンを置くチャンネルのID
"""
import os
import sys

import requests

# worker.js の MEMBERS と同じ並びにすること
MEMBERS = ["さくちゃん", "おいどん", "あるの", "うるねぇ", "さくたん",
           "てれぱん", "おかひな", "まゆたん", "さやっち", "その他"]


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel = os.environ.get("DISCORD_BUTTON_CHANNEL_ID")
    if not token or not channel:
        sys.exit("DISCORD_BOT_TOKEN と DISCORD_BUTTON_CHANNEL_ID を設定してください")

    buttons = [
        {"type": 2, "style": 2, "label": n, "custom_id": f"photo:{n}"} for n in MEMBERS
    ]
    buttons.append({"type": 2, "style": 1, "label": "🎲 ランダム", "custom_id": "photo:__random__"})
    rows = [{"type": 1, "components": buttons[i:i + 5]} for i in range(0, len(buttons), 5)]

    r = requests.post(
        f"https://discord.com/api/v10/channels/{channel}/messages",
        json={"content": "📷 **推しの写真**\n名前を押すと写真が見られます(押した人にだけ表示されます)", "components": rows},
        headers={"Authorization": f"Bot {token}"},
        timeout=30,
    )
    if not r.ok:
        sys.exit(f"Discord送信エラー {r.status_code}: {r.text}")
    print("ボタンを設置しました")


if __name__ == "__main__":
    main()
