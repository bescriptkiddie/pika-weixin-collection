import unittest
from unittest.mock import Mock, patch

import api
from src.crawler.wechat_request import WechatRequest
from src.utils import helpers
from src.utils.data_manager import headers as global_headers


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class WechatRequestTests(unittest.TestCase):
    def test_init_uses_isolated_headers_and_disables_env_proxy(self):
        with patch("src.crawler.wechat_request.data_manager.id_info", {"cookie": "cookie-a", "token": "token-a"}):
            req = WechatRequest(auto_login=False)

        self.assertIsNot(req.headers, global_headers)
        self.assertEqual(req.headers["Cookie"], "cookie-a")
        self.assertFalse(req.session.trust_env)

    def test_name2fakeid_retry_uses_instance_headers(self):
        first_response = FakeResponse({"base_resp": {"err_msg": "invalid session"}, "list": []})
        second_response = FakeResponse({
            "base_resp": {"err_msg": "ok"},
            "list": [{"nickname": "目标号", "fakeid": "fake-id"}],
        })
        session = Mock()
        session.get.side_effect = [first_response, second_response]

        with patch("src.crawler.wechat_request.data_manager.id_info", {"cookie": "cookie-a", "token": "token-a"}):
            req = WechatRequest(auto_login=True)

        req.session = session

        def fake_overdue(response):
            if response["base_resp"]["err_msg"] == "invalid session":
                req.token = "token-b"
                req.headers["Cookie"] = "cookie-b"
                return True
            return False

        with patch.object(req, "session_is_overdue", side_effect=fake_overdue):
            fakeid = req.name2fakeid("目标号")

        self.assertEqual(fakeid, "fake-id")
        self.assertEqual(session.get.call_count, 2)
        first_headers = session.get.call_args_list[0].kwargs["headers"]
        second_headers = session.get.call_args_list[1].kwargs["headers"]
        self.assertIs(first_headers, req.headers)
        self.assertIs(second_headers, req.headers)
        self.assertEqual(second_headers["Cookie"], "cookie-b")
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["token"], "token-b")


class AuthCheckTests(unittest.TestCase):
    def test_check_auth_valid_returns_transport_error(self):
        session = Mock()
        session.get.side_effect = OSError("dns boom")

        with patch("requests.Session", return_value=session), patch(
            "src.utils.data_manager.data_manager.id_info",
            {"token": "token-a", "cookie": "cookie-a"},
        ):
            status, reason = api._check_auth_valid()

        self.assertEqual(status, "transport_error")
        self.assertIn("dns boom", reason)
        self.assertFalse(session.trust_env)


class HelperRequestTests(unittest.TestCase):
    def test_message_is_delete_uses_bounded_session_request(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            text='<div class="weui-msg__title warn">该内容已被发布者删除</div>'
        )

        with patch("src.utils.helpers.requests.Session", return_value=session):
            deleted = helpers.message_is_delete(url="https://example.com/article")

        self.assertTrue(deleted)
        self.assertFalse(session.trust_env)
        self.assertEqual(session.get.call_args.kwargs["timeout"], 15)
        self.assertIsNot(session.get.call_args.kwargs["headers"], helpers.headers)


if __name__ == "__main__":
    unittest.main()
