# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""核心引擎测试"""

import pytest

from core.app import app


class TestApp:
    """App 测试"""

    def test_app_exists(self):
        assert app is not None

    def test_app_has_tools(self):
        tools = app.get_tools()
        assert len(tools) >= 2

    def test_app_has_agent(self):
        graphs = app._graphs
        assert "main" in graphs

    def test_get_tool_schemas(self):
        schemas = app.get_tool_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 2
