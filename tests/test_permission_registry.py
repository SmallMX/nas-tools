import ast
import unittest
from pathlib import Path

from web.permissions import CMD_PERMISSIONS, PATH_PERMISSIONS, PUBLIC_PATHS


ROOT = Path(__file__).resolve().parents[1]


class PermissionRegistryTest(unittest.TestCase):
    def test_all_web_actions_have_permission_rule(self):
        tree = ast.parse((ROOT / "web" / "action.py").read_text(encoding="utf-8"))
        actions = set()
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
            actions.update(
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )

        missing = sorted(actions.difference(CMD_PERMISSIONS))
        self.assertEqual([], missing, f"以下 Web 动作缺少权限声明：{missing}")

    def test_all_ui_routes_are_public_or_have_permission_rule(self):
        routes = set()
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
                        routes.add(route.value.rstrip("/"))

        special_routes = {"/", "/do"}
        missing = sorted(routes.difference(PATH_PERMISSIONS, PUBLIC_PATHS, special_routes))
        self.assertEqual([], missing, f"以下 UI 路由缺少权限声明：{missing}")


if __name__ == "__main__":
    unittest.main()
