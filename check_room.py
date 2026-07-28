import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright


# 監視対象はここへ追加します。
WATCH_TARGETS = [
    {
        "hotel_name": "東横INN札幌駅南口",
        "area": "429",
        "check_in": "2026-09-04",
        "check_out": "2026-09-05",
        "people": 1,
        "rooms": 1,
        "smoking": "noSmoking",
    },
    {
        "hotel_name": "東横INN札幌すすきの交差点",
        "area": "429",
        "check_in": "2026-09-04",
        "check_out": "2026-09-05",
        "people": 1,
        "rooms": 1,
        "smoking": "noSmoking",
    },
]

STATE_FILE = Path("room_state.json")


def build_url(target: dict) -> str:
    """監視対象の検索URLを作る。"""
    params = {
        "area": target["area"],
        "people": target["people"],
        "room": target["rooms"],
        "smoking": target["smoking"],
        "start": target["check_in"],
        "end": target["check_out"],
    }

    return (
        "https://www.toyoko-inn.com/search/result/?"
        + urlencode(params)
    )


def get_hotel_section(page_text: str, hotel_name: str) -> str:
    """対象ホテルから次の東横INNホテルまでの文章を切り出す。"""
    start = page_text.find(hotel_name)

    if start == -1:
        raise RuntimeError(
            f"ホテルが検索結果に見つかりませんでした: {hotel_name}"
        )

    next_hotel = page_text.find(
        "東横INN",
        start + len(hotel_name),
    )

    if next_hotel == -1:
        return page_text[start:]

    return page_text[start:next_hotel]


def load_state() -> dict:
    """前回の空室状況を読み込む。"""
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    """今回の空室状況を保存する。"""
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def make_target_key(target: dict) -> str:
    """ホテルと日程ごとの識別名を作る。"""
    return (
        f'{target["hotel_name"]}'
        f'|{target["check_in"]}'
        f'|{target["check_out"]}'
    )


def format_date(date_text: str) -> str:
    """2026-09-04を2026年9月4日に変換する。"""
    year, month, day = date_text.split("-")

    return f"{int(year)}年{int(month)}月{int(day)}日"


def send_email(subject: str, body: str) -> None:
    """GmailからYahooメールへ通知を送る。"""
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ["TO_EMAIL"]

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = gmail_user
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
    ) as smtp:
        smtp.login(
            gmail_user,
            gmail_app_password,
        )
        smtp.send_message(message)


def check_target(page, target: dict) -> bool:
    """ホテルを確認し、空室があればTrueを返す。"""
    hotel_name = target["hotel_name"]
    url = build_url(target)

    print("")
    print("=" * 60)
    print(f"確認中: {hotel_name}")
    print(
        f'日程: {target["check_in"]}'
        f' ～ {target["check_out"]}'
    )
    print("=" * 60)

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    page.wait_for_timeout(5000)

    body_text = page.locator("body").inner_text()
    hotel_section = get_hotel_section(
        body_text,
        hotel_name,
    )

    print("\n--- 対象ホテルの表示内容 ---")
    print(hotel_section)
    print("--- ここまで ---\n")

    if "空室なし" in hotel_section:
        print(f"結果: {hotel_name} は空室なしです")
        return False

    print(
        f"結果: {hotel_name} に"
        "空室がある可能性があります"
    )
    return True


def notify_available(target: dict) -> None:
    """空室通知メールを送る。"""
    hotel_name = target["hotel_name"]
    url = build_url(target)

    check_in = format_date(target["check_in"])
    check_out = format_date(target["check_out"])

    subject = f"【空室通知】{hotel_name}"

    body = f"""
{hotel_name} に空室がある可能性があります。

宿泊日：
{check_in} ～ {check_out}

{target["people"]}名・{target["rooms"]}室・禁煙

予約ページ：
{url}

空室はすぐ埋まる可能性があるため、早めに確認してください。
""".strip()

    send_email(subject, body)
    print("通知メールを送信しました")


def main() -> None:
    print("東横INNの空室確認を開始します")

    previous_state = load_state()
    current_state = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1000,
            }
        )

        for target in WATCH_TARGETS:
            target_key = make_target_key(target)

            try:
                is_available = check_target(
                    page,
                    target,
                )
            except Exception as error:
                print(
                    f'確認エラー: '
                    f'{target["hotel_name"]}: {error}'
                )
                current_state[target_key] = (
                    previous_state.get(
                        target_key,
                        False,
                    )
                )
                continue

            current_state[target_key] = is_available

            was_available = previous_state.get(
                target_key,
                False,
            )

            if is_available and not was_available:
                notify_available(target)

            elif is_available and was_available:
                print(
                    "前回から引き続き空室ありのため、"
                    "メールは送りません"
                )

        browser.close()

    save_state(current_state)
    print("\nすべての確認が終了しました")


if __name__ == "__main__":
    main()
