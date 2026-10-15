import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.preview_ui import PAGES, VARIANTS, create_preview_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web/static"
IMPORTS = re.compile(r"(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?[\"']([^\"']+)[\"']")


class PageMarkup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


class FrontendAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 真实模板使用内存示例渲染；不读取运行配置，也不访问业务服务。
        client = create_preview_app().test_client()
        paths = ["/", "/preview/login", *["/" + path for path in PAGES],
                 *["/" + path for path in VARIANTS],
                 *[f"/preview/error/{code}" for code in (403, 404, 500)]]
        cls.pages = {}
        for path in paths:
            response = client.get(path)
            if response.status_code != 200:
                raise AssertionError(f"预览模板渲染失败：{path} ({response.status_code})")
            source = response.get_data(as_text=True)
            cls.pages[path] = (source, PageMarkup(source))

    def assert_resource_exists(self, reference, parent):
        parsed = urlsplit(reference.strip())
        if parsed.scheme or parsed.netloc or not parsed.path:
            return None
        path = unquote(parsed.path)
        if "/static/" in path:
            target = STATIC / path.split("/static/", 1)[1]
        else:
            target = parent / path
        self.assertTrue(target.is_file(), f"静态引用缺失：{parent.relative_to(ROOT)} -> {reference}")
        return target.resolve()

    def test_rendered_template_and_manifest_assets_exist(self):
        references = set()
        for _, markup in self.pages.values():
            for _, attrs in markup.elements:
                for attr in ("src", "href", "poster"):
                    reference = attrs.get(attr) or ""
                    if "/static/" in reference:
                        references.add(reference)
                references.update(re.findall(r"url\(['\"]?([^)'\"]+)", attrs.get("style") or ""))
        self.assertGreater(len(references), 40, "未能提取模板中的静态资源")
        for reference in sorted(references):
            if "/static/" in reference:
                with self.subTest(reference=reference):
                    self.assert_resource_exists(reference, ROOT / "web/templates")
        manifest = json.loads((STATIC / "site.webmanifest").read_text())
        for icon in manifest["icons"]:
            self.assert_resource_exists(icon["src"], STATIC)

    def test_stylesheet_urls_and_javascript_module_imports_exist(self):
        for stylesheet in STATIC.rglob("*.css"):
            for reference in re.findall(r"url\(\s*([^)]+)\)", stylesheet.read_text()):
                with self.subTest(file=stylesheet.relative_to(ROOT), reference=reference[:120]):
                    self.assert_resource_exists(reference.strip("\"' "), stylesheet.parent)
        for script in STATIC.rglob("*.js"):
            for reference in IMPORTS.findall(script.read_text()):
                if reference.startswith("."):
                    with self.subTest(file=script.relative_to(ROOT), reference=reference):
                        self.assert_resource_exists(reference, script.parent)

    def test_component_entrypoints_and_dynamic_editor_dependencies_are_reachable(self):
        entries = set()
        for _, markup in self.pages.values():
            for tag, attrs in markup.elements:
                if tag == "script" and "/static/" in (attrs.get("src") or ""):
                    entries.add(self.assert_resource_exists(attrs["src"], ROOT / "web/templates"))
        reachable = set()
        pending = list(entries)
        while pending:
            script = pending.pop()
            if script in reachable:
                continue
            reachable.add(script)
            pending.extend((script.parent / reference).resolve()
                           for reference in IMPORTS.findall(script.read_text()) if reference.startswith("."))
        for script in (STATIC / "components").rglob("*.js"):
            self.assertIn(script.resolve(), reachable, f"组件没有加载入口：{script.relative_to(ROOT)}")
        # 经典组件入口通过 jQuery.load 加载 chips，而非 ES module import。
        loader = STATIC / "components/index.js"
        self.assertIn(loader.resolve(), reachable)
        for reference in re.findall(r'["\']([^"\']+\.html)["\']', loader.read_text()):
            self.assert_resource_exists(reference, loader.parent)
        editor_modes = set()
        for source, _ in self.pages.values():
            for kind, name in re.findall(r"ace/(mode|theme)/([\w-]+)", source):
                self.assert_resource_exists(f"{kind}-{name}.js", STATIC / "js")
                if kind == "mode":
                    editor_modes.add(name)
        self.assertEqual({"css", "javascript"}, editor_modes)
        for name in editor_modes:
            self.assert_resource_exists(f"worker-{name}.js", STATIC / "js")

    def test_application_markup_has_no_executable_event_attributes(self):
        # 只检查项目应用模板；不解析用户脚本内容或 Flask-RESTX 的第三方页面。
        violations = []
        for path, (_, markup) in self.pages.items():
            for tag, attrs in markup.elements:
                for name, value in attrs.items():
                    if name.lower().startswith("on") or (
                            name in {"href", "src", "action", "formaction"}
                            and (value or "").lstrip().lower().startswith("javascript:")):
                        violations.append(f"{path}: <{tag}> {name}={value}")
        # 模板脚本中的动态 HTML 也不能重新引入内联事件。自定义脚本来自运行配置，
        # 不属于这些仓库源文件；第三方压缩库不参与这项应用代码约束。
        sources = [*(ROOT / "web/templates").rglob("*.html"),
                   *(STATIC / "components").rglob("*.js"),
                   *(STATIC / "components").rglob("*.html")]
        executable_attribute = re.compile(
            r"<[a-z][^>]*?\s(on[a-z]+\s*=|(?:href|src|action|formaction)\s*=\s*[\"']\s*javascript:)",
            re.IGNORECASE)
        for source in sources:
            if source.name.endswith(".min.js"):
                continue
            for match in executable_attribute.finditer(source.read_text()):
                violations.append(f"{source.relative_to(ROOT)}: {match.group(1)}")
        self.assertEqual([], violations, "应用交互应通过 data 属性和事件绑定，不拼接可执行属性")


if __name__ == "__main__":
    unittest.main()
