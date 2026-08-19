import os
import json
import time
import base64
import subprocess
from pathlib import Path

from PIL import Image
from groq import Groq


# =========================================================
# CONFIG
# =========================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    raise RuntimeError(
        "Chưa set GROQ_API_KEY environment variable"
    )

MAIN_FRIEND_LINK = (
    "https://link.haydaygame.com/"
    "?action=OpenSCID"
    "&p=66-0afacf13-262f-4cd9-8d0d-224e59df3cac"
)

ACCOUNTS_FILE = Path("accounts.json")
STATE_FILE = Path("state.json")
SCREENSHOT_FILE = Path("screen.png")

MAX_ACTIONS = 250


# =========================================================
# GROQ CLIENT
# =========================================================

client = Groq(
    api_key=GROQ_API_KEY
)


# =========================================================
# STATE
# =========================================================

def load_accounts():
    with open(
        ACCOUNTS_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    return data.get("accounts", [])


def load_state():
    if not STATE_FILE.exists():
        return {
            "current_index": 0,
            "completed": []
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {
            "current_index": 0,
            "completed": []
        }


def save_state(state):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            state,
            f,
            indent=2,
            ensure_ascii=False
        )


# =========================================================
# ADB
# =========================================================

def adb(*args, check=True):

    command = [
        "adb",
        *args
    ]

    print(
        "ADB:",
        " ".join(command)
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"ADB command failed: {result.returncode}"
        )

    return result


def tap(x, y):

    adb(
        "shell",
        "input",
        "tap",
        str(int(x)),
        str(int(y))
    )


def swipe(
    x1,
    y1,
    x2,
    y2,
    duration=500
):

    adb(
        "shell",
        "input",
        "swipe",
        str(int(x1)),
        str(int(y1)),
        str(int(x2)),
        str(int(y2)),
        str(int(duration))
    )


def press_back():

    adb(
        "shell",
        "input",
        "keyevent",
        "4"
    )


def wait(seconds):

    time.sleep(seconds)


def screenshot():

    result = subprocess.run(
        [
            "adb",
            "exec-out",
            "screencap",
            "-p"
        ],
        capture_output=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Không chụp được screenshot"
        )

    data = result.stdout.replace(
        b"\r\n",
        b"\n"
    )

    with open(
        SCREENSHOT_FILE,
        "wb"
    ) as f:
        f.write(data)

    return Image.open(
        SCREENSHOT_FILE
    )


# =========================================================
# OPEN MAIN FRIEND LINK
# =========================================================

def open_main_friend_link():

    print("")
    print("==========================================")
    print("🔗 MỞ LINK KẾT BẠN ACC CHÍNH")
    print("==========================================")

    # Dùng Android VIEW intent để mở link
    adb(
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        MAIN_FRIEND_LINK
    )

    wait(5)

    print("✅ Đã mở link acc chính.")


# =========================================================
# AI PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are controlling a Hay Day Android game using screenshots
and ADB.

Your job is to choose ONE safe action at a time.

Allowed actions:

tap
swipe
back
wait
friend_link
done

Return ONLY JSON.

Tap format:

{
  "action": "tap",
  "x": 500,
  "y": 300,
  "reason": "..."
}

Swipe format:

{
  "action": "swipe",
  "x": 500,
  "y": 500,
  "x2": 500,
  "y2": 200,
  "duration": 500,
  "reason": "..."
}

Wait:

{
  "action": "wait",
  "duration": 3,
  "reason": "..."
}

Friend link:

{
  "action": "friend_link",
  "reason": "The game is ready for the friend step."
}

Done:

{
  "action": "done",
  "reason": "The requested operation is complete."
}

Rules:

- Only act on UI elements visible in the screenshot.
- Do not guess coordinates if the target is not visible.
- Prefer waiting when the game is loading.
- Do not buy anything.
- Do not delete anything.
- Do not change security settings.
- Do not create accounts.
- Do not enter passwords or OTP codes.
- Do not repeatedly spam the same button.
"""


# =========================================================
# IMAGE -> BASE64
# =========================================================

def image_to_base64(image):

    import io

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG"
    )

    buffer.seek(0)
    
    return base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")


# =========================================================
# ASK AI
# =========================================================

def ask_ai(
    image,
    account_id
):

    prompt = f"""
Current account:

{account_id}

Main objective:

Play Hay Day until the account reaches the point where
the required friend/shop operation can be performed.

When the game is visibly ready for the friend step,
use:

friend_link

After the friend operation is complete,
use:

done

Return JSON only.
"""

    image_base64 = image_to_base64(image)

    response = client.chat.completions.create(
        model="llama-2-vision-90b",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT + "\n\n" + prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        temperature=0.1,
        max_tokens=1024
    )

    text = response.choices[0].message.content.strip()

    print("")
    print("========== AI ==========")
    print(text)
    print("========================")

    if text.startswith("```"):
        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    return json.loads(text)


# =========================================================
# EXECUTE AI ACTION
# =========================================================

def execute_action(result):

    action = result.get(
        "action"
    )

    reason = result.get(
        "reason",
        ""
    )

    print(
        f"🤖 {action}: {reason}"
    )

    if action == "tap":

        tap(
            result["x"],
            result["y"]
        )

        wait(1)

        return False

    if action == "swipe":

        swipe(
            result["x"],
            result["y"],
            result["x2"],
            result["y2"],
            result.get(
                "duration",
                500
            )
        )

        wait(1)

        return False

    if action == "back":

        press_back()

        wait(1)

        return False

    if action == "wait":

        wait(
            result.get(
                "duration",
                2
            )
        )

        return False

    if action == "friend_link":

        open_main_friend_link()

        return False

    if action == "done":

        return True

    print(
        "⚠️ Action không hợp lệ:",
        action
    )

    wait(2)

    return False


# =========================================================
# RUN ACCOUNT
# =========================================================

def run_account(
    account_id
):

    print("")
    print("==========================================")
    print("🎮 ACCOUNT:", account_id)
    print("==========================================")

    for action_number in range(
        1,
        MAX_ACTIONS + 1
    ):

        print("")
        print(
            f"----- ACTION "
            f"{action_number}/{MAX_ACTIONS} -----"
        )

        try:

            image = screenshot()

            result = ask_ai(
                image,
                account_id
            )

            finished = execute_action(
                result
            )

            if finished:

                print(
                    "✅ Hoàn thành:",
                    account_id
                )

                return True

        except Exception as e:

            print(
                "❌ Lỗi:",
                repr(e)
            )

            # Lưu screenshot để debug
            try:
                screenshot()
            except Exception:
                pass

            wait(5)

    print(
        "⚠️ Đã đạt giới hạn action:",
        account_id
    )

    return False


# =========================================================
# MAIN
# =========================================================

def main():

    print("==========================================")
    print("🤖 HAY DAY AI BOT")
    print("==========================================")

    accounts = load_accounts()

    if not accounts:

        raise RuntimeError(
            "accounts.json không có tài khoản."
        )

    state = load_state()

    completed = set(
        state.get(
            "completed",
            []
        )
    )

    current_index = state.get(
        "current_index",
        0
    )

    print(
        "📋 Tổng acc:",
        len(accounts)
    )

    print(
        "✅ Đã hoàn thành:",
        list(completed)
    )

    for index in range(
        current_index,
        len(accounts)
    ):

        account = accounts[index]

        account_id = account.get(
            "id"
        )

        if not account_id:
            continue

        if account_id in completed:

            print(
                "⏭️ Bỏ qua:",
                account_id
            )

            continue

        state["current_index"] = index

        save_state(state)

        success = run_account(
            account_id
        )

        if success:

            completed.add(
                account_id
            )

            state["completed"] = list(
                completed
            )

            state["current_index"] = (
                index + 1
            )

            save_state(state)

            print(
                "💾 Đã lưu trạng thái."
            )

            wait(5)

        else:

            print(
                "🛑 Account chưa hoàn thành:"
            )

            print(
                account_id
            )

            save_state(state)

            break

    print("")
    print("==========================================")
    print("🏁 KẾT THÚC")
    print("==========================================")

    print(
        "Completed:",
        list(completed)
    )


if __name__ == "__main__":
    main()
