import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROUTES = {"/", "/healthz", "/robots.txt", "/telegram"}


class AuthenticationBoundaryTest(unittest.TestCase):
    def test_web_actions_have_unique_registration(self):
        tree = ast.parse((ROOT / "web" / "action.py").read_text(encoding="utf-8"))
        actions = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            if not any(
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr == "_actions"
                    for target in node.targets):
                continue
            actions.extend(
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )

        self.assertTrue(actions, "未找到 Web 动作注册表，不能跳过注册检查")
        self.assertEqual(len(actions), len(set(actions)), "Web 动作存在重复注册")
        self.assertTrue({"get_users", "user_manager"}.isdisjoint(actions))

    def test_all_private_ui_routes_require_login(self):
        routes = set()
        missing = []
        route_files = [ROOT / "web" / "main.py", *(ROOT / "web" / "routes").glob("*.py")]
        for route_file in route_files:
            tree = ast.parse(route_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not decorator.args:
                        continue
                    func = decorator.func
                    if not isinstance(func, ast.Attribute) or func.attr != "route":
                        continue
                    route = decorator.args[0]
                    if isinstance(route, ast.Constant) and isinstance(route.value, str):
                        path = route.value
                        routes.add(path)
                        if path in PUBLIC_ROUTES:
                            continue
                        authentication = "action_login_check" if path == "/do" else "login_required"
                        if not any(isinstance(item, ast.Name) and item.id == authentication
                                   for item in node.decorator_list):
                            missing.append(path)

        self.assertTrue(routes, "未找到 UI 路由，不能跳过登录认证检查")
        self.assertTrue(PUBLIC_ROUTES.issubset(routes))
        self.assertIn("/do", routes)
        self.assertNotIn("/users", routes)
        self.assertEqual([], sorted(missing), f"以下 UI 路由缺少登录认证：{missing}")


if __name__ == "__main__":
    unittest.main()
