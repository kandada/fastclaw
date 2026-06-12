import subprocess
import platform


async def execute(message: str = None, recipient: str = None, **kwargs) -> str:
    """iMessage 技能（仅支持 Mac）

    Args:
        message: 消息内容
        recipient: 收件人（电话号码或邮箱）
    """
    if platform.system() != "Darwin":
        return "Error: iMessage is only available on Mac"

    if not message:
        return "Error: message is required"

    if not recipient:
        return "Error: recipient is required"

    script = f'''
    osascript -e '
    tell application "Messages"
        set targetService to 1
        set targetBuddy to "{recipient}"
        set msg to "{message.replace('"', '\\"')}"
        send msg to buddy targetBuddy of service id targetService
    end tell
    '
    '''

    try:
        result = subprocess.run(
            script,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return f"Error: AppleScript error: {result.stderr}"

        return f"Message sent successfully to {recipient}"

    except subprocess.TimeoutExpired:
        return "Error: iMessage send timed out"
    except Exception as e:
        return f"Error: Failed to send iMessage: {str(e)}"
