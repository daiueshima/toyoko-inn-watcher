import os
import smtplib
from email.message import EmailMessage

from playwright.sync_api import sync_playwright


URL = (
    "https://www.toyoko-inn.com/search/result/"
    "?area=429"
    "&people=1"
    "&room=1"
    "&smoking=noSmoking"
    "&start=2026-09-04"
    "&end=2026-09-05"
)

HOTEL_NAME = "東横INN札幌駅南口"
CHECK_IN = "2026年9月4日"
CHECK_OUT = "2026年9月5日"


def get_hotel_section(page_text: str, hotel_name: str) -> str:
    """対象ホテルから次の東横INNホテルまでの文章を切り出す。"""
    start = page_text.find(hotel_name)

    if start == -1:
        raise RuntimeError(f"ホテルが見つかりませんでした: {hotel_name}")

    next_hotel = page_text.find("東横INN", start + len(hotel_name))

    if next_hotel == -1:
        return page_text[start:]

    return page_text[start:next_hotel]


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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(message)


def main() -> None:
    print("東横INNの空室確認を開始します")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        page.wait_for_timeout(5000)

        body_text = page.locator("body").inner_text()
        hotel_section = get_hotel_section(body_text, HOTEL_NAME)

        print("\n--- 対象ホテルの表示内容 ---")
        print(hotel_section)
        print("--- ここまで ---\n")

        browser.close()

    if "空室なし" in hotel_section:
        print(f"結果: {HOTEL_NAME} は空室なしです")
        return

    print(f"結果: {HOTEL_NAME} に空室がある可能性があります")

    subject = f"【空室通知】{HOTEL_NAME}"

    body = f"""
{HOTEL_NAME} に空室がある可能性があります。

宿泊日：
{CHECK_IN} ～ {CHECK_OUT}

1名・1室・禁煙

予約ページ：
{URL}

空室はすぐ埋まる可能性があるため、早めに確認してください。
""".strip()

    send_email(subject, body)
    print("通知メールを送信しました")


if __name__ == "__main__":
    main()