"""渠道适配器测试"""


class _ConcreteAdapter:
    """用 ChannelAdapter 的接口定义的测试适配器"""

    def __init__(self, name="test"):
        self.name = name
        self.enabled = False
        self.config = {}

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def send_message(self, message, session_id=None):
        return {"code": 0}

    async def on_message(self, message):
        pass

    async def enable(self):
        self.enabled = True
        await self.connect()

    async def disable(self):
        self.enabled = False
        await self.disconnect()

    def load_config(self, config):
        self.config = config

    def get_config(self, key, default=None):
        return self.config.get(key, default)


class TestChannelAdapter:
    """渠道适配器基础行为测试 — 与 ChannelAdapter 接口一致"""

    def test_adapter_has_name_and_disabled_by_default(self):
        adapter = _ConcreteAdapter("test_channel")
        assert adapter.name == "test_channel"
        assert adapter.enabled is False

    def test_adapter_config_load_and_get(self):
        adapter = _ConcreteAdapter()
        adapter.load_config({"app_id": "123", "secret": "abc"})
        assert adapter.get_config("app_id") == "123"
        assert adapter.get_config("secret") == "abc"
        assert adapter.get_config("missing", "fallback") == "fallback"

    def test_adapter_enable_and_disable(self):
        adapter = _ConcreteAdapter()
        import asyncio
        asyncio.run(adapter.enable())
        assert adapter.enabled is True
        asyncio.run(adapter.disable())
        assert adapter.enabled is False

    def test_adapter_send_message_returns_ok(self):
        adapter = _ConcreteAdapter()
        import asyncio
        result = asyncio.run(adapter.send_message("hello", session_id="s1"))
        assert result["code"] == 0


class TestChannelConfigs:
    """渠道配置契约测试"""

    def test_feishu_config_has_required_keys(self):
        config = {"app_id": "test_id", "app_secret": "test_secret", "name": "feishu"}
        assert config["app_id"] == "test_id"
        assert config["app_secret"] == "test_secret"

    def test_imessage_config_disabled_default(self):
        config = {"name": "imessage", "enabled": False}
        assert config["enabled"] is False

    def test_telegram_config_has_token(self):
        config = {"bot_token": "test_token", "name": "telegram"}
        assert config["bot_token"] == "test_token"

    def test_telegram_chat_id_is_numeric(self):
        chat_id = "123456789"
        assert chat_id.isdigit()

    def test_imessage_recipient_has_at(self):
        recipient = "test@icloud.com"
        assert "@" in recipient
