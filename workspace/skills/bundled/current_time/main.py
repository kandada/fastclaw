from datetime import datetime


async def execute(**kwargs) -> str:
    """获取当前时间"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
