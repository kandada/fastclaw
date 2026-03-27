"""Skill template - 修改这个文件创建你自己的技能"""


async def execute(**kwargs) -> str:
    """执行技能

    Args:
        **kwargs: 技能参数

    Returns:
        str: 执行结果
    """
    param1 = kwargs.get("param1", "")
    param2 = kwargs.get("param2", "")

    # 在这里实现你的技能逻辑
    result = f"Received param1={param1}, param2={param2}"

    return result
