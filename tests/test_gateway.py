"""Gateway 测试"""

import pytest
import uuid
from tests.conftest import cleanup_test_session


class TestRouter:
    """Router 测试"""

    def test_health_check(self):
        """测试健康检查端点"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_session_create(self):
        """测试创建 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.post("/api/sessions", json={})
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert "agent_id" in data

            cleanup_test_session(data["session_id"])

    def test_session_create_with_agent(self):
        """测试指定 agent 创建 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.post("/api/sessions", json={"agent_id": "main_agent"})
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "main_agent"

            cleanup_test_session(data["session_id"])

    def test_session_list(self):
        """测试列出 sessions"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.post("/api/sessions", json={})
            session_id = response.json()["session_id"]

            response = client.get("/api/sessions")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

            cleanup_test_session(session_id)

    def test_session_get(self):
        """测试获取指定 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            create_resp = client.post("/api/sessions", json={})
            session_id = create_resp.json()["session_id"]

            response = client.get(f"/api/sessions/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id

            cleanup_test_session(session_id)

    def test_session_get_not_found(self):
        """测试获取不存在的 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/sessions/nonexistent")
            assert response.status_code == 404

    def test_session_update(self):
        """测试更新 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            create_resp = client.post("/api/sessions", json={})
            session_id = create_resp.json()["session_id"]

            response = client.patch(
                f"/api/sessions/{session_id}", json={"agent_id": "main_agent"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "main_agent"

            cleanup_test_session(session_id)

    def test_session_delete(self):
        """测试删除 session"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            create_resp = client.post("/api/sessions", json={})
            session_id = create_resp.json()["session_id"]

            response = client.delete(f"/api/sessions/{session_id}")
            assert response.status_code == 200

            get_resp = client.get(f"/api/sessions/{session_id}")
            assert get_resp.status_code == 404

    def test_session_messages_get(self):
        """测试获取 session 消息历史"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/sessions/test_session/messages")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_session_messages_delete(self):
        """测试清空 session 消息历史"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.delete("/api/sessions/test_session/messages")
            assert response.status_code == 200
            assert response.json()["status"] == "cleared"


class TestSettingsAPI:
    """设置 API 测试"""

    def test_settings_get(self):
        """测试获取设置"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/settings")
            assert response.status_code == 200
            data = response.json()
            assert "default_agent_id" in data

    def test_settings_put(self):
        """测试更新设置"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.put(
                "/api/settings", json={"default_agent_id": "main_agent"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            assert data["settings"]["default_agent_id"] == "main_agent"


class TestCronAPI:
    """Cron API 测试"""

    def test_crons_get(self):
        """测试获取 cron 任务列表"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/crons")
            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data
            assert isinstance(data["tasks"], list)

    def test_crons_create(self):
        """测试创建 cron 任务"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        task_id = f"test_cron_{uuid.uuid4().hex[:8]}"

        with TestClient(server.app) as client:
            task_data = {
                "id": task_id,
                "name": "Test Task",
                "schedule": "0 9 * * *",
                "description": "Test description",
                "agent_id": "main_agent",
                "enabled": True,
            }
            response = client.post("/api/crons", json=task_data)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "created"
            assert data["task"]["id"] == task_id

            client.delete(f"/api/crons/{task_id}")

    def test_crons_create_all_stars_rejected(self):
        """测试全*的cron表达式被拒绝"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()
        task_id = f"test_cron_{uuid.uuid4().hex[:8]}"

        with TestClient(server.app) as client:
            task_data = {
                "id": task_id,
                "name": "Test Task",
                "schedule": "* * * * *",
                "agent_id": "main_agent",
            }
            response = client.post("/api/crons", json=task_data)
            assert response.status_code == 400
            assert "cannot be all" in response.json()["detail"]

    def test_crons_create_missing_required_field(self):
        """测试缺少必填字段被拒绝"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()
        task_id = f"test_cron_{uuid.uuid4().hex[:8]}"

        with TestClient(server.app) as client:
            task_data = {
                "id": task_id,
                "name": "Test Task",
            }
            response = client.post("/api/crons", json=task_data)
            assert response.status_code == 400
            assert "schedule" in response.json()["detail"]

    def test_crons_create_defaults_applied(self):
        """测试默认值被正确填充"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()
        task_id = f"test_cron_{uuid.uuid4().hex[:8]}"

        with TestClient(server.app) as client:
            task_data = {
                "id": task_id,
                "name": "Test Task",
                "schedule": "0 9 * * *",
            }
            response = client.post("/api/crons", json=task_data)
            assert response.status_code == 200
            data = response.json()
            assert data["task"]["description"] == ""
            assert data["task"]["agent_id"] == "main_agent"
            assert data["task"]["enabled"] is True
            assert data["task"]["session_id"] is None

            client.delete(f"/api/crons/{task_id}")

    def test_crons_delete(self):
        """测试删除 cron 任务"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        task_id = f"test_cron_del_{uuid.uuid4().hex[:8]}"

        with TestClient(server.app) as client:
            client.post(
                "/api/crons",
                json={
                    "id": task_id,
                    "name": "To Delete",
                    "schedule": "0 9 * * *",
                    "agent_id": "main_agent",
                    "enabled": True,
                },
            )

            response = client.delete(f"/api/crons/{task_id}")
            assert response.status_code == 200
            assert response.json()["status"] == "deleted"

    def test_crons_trigger_not_found(self):
        """测试触发不存在的 cron 任务（API未初始化时返回500）"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.post(
                "/api/crons/trigger", json={"task_id": "nonexistent_task"}
            )
            assert response.status_code in (404, 500)


class TestSkillsAgentsAPI:
    """Skills 和 Agents API 测试"""

    def test_skills_get(self):
        """测试获取技能列表"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/skills")
            assert response.status_code == 200
            data = response.json()
            assert "skills" in data
            assert "skills_list" in data

    def test_agents_get(self):
        """测试获取 Agent 列表"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert isinstance(data["agents"], list)


class TestRouterAPI:
    """Router API 路由测试"""

    def test_api_prefix(self):
        """测试 /api 前缀"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200


class TestWebUIStaticFiles:
    """WebUI 静态文件测试"""

    def test_webui_index(self):
        """测试 WebUI 首页"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    def test_webui_static_css(self):
        """测试 WebUI CSS 文件"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/webui/static/css/element-plus.css")
            assert response.status_code == 200
            assert "text/css" in response.headers["content-type"]

    def test_webui_static_js(self):
        """测试 WebUI JS 文件"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()

        with TestClient(server.app) as client:
            response = client.get("/webui/static/js/vue3.prod.js")
            assert response.status_code == 200
            assert "javascript" in response.headers["content-type"]
