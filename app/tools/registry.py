"""内置工具的静态注册表。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSource:
    """记录移植工具的上游来源，便于审计和后续同步。"""

    repository: str
    path: str
    revision: str
    author: str
    license: str

    def __post_init__(self):
        if any(
                not isinstance(value, str) or not value.strip()
                for value in (
                    self.repository, self.path, self.revision, self.author, self.license
                )
        ):
            raise ValueError("外部工具来源信息必须完整")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """描述一个随项目发布的内置工具。"""

    tool_id: str
    name: str
    description: str
    page: str
    permission: str
    icon: str
    order: int = 9999
    source: ToolSource | None = None


_TOOLS = (
    ToolDefinition(
        tool_id="site_signin",
        name="站点自动签到",
        description="执行站点签到或保号登录，并查看今日状态与最近执行历史。",
        page="tools/site-signin",
        permission="站点管理",
        icon="sign_in.svg",
        order=10,
    ),
)

_TOOLS_BY_ID = {tool.tool_id: tool for tool in _TOOLS}
if len(_TOOLS_BY_ID) != len(_TOOLS):
    raise RuntimeError("内置工具 ID 不能重复")


def get_tools() -> tuple[ToolDefinition, ...]:
    """按展示顺序返回全部内置工具。"""
    return tuple(sorted(_TOOLS, key=lambda tool: (tool.order, tool.tool_id)))


def get_tool(tool_id: str | None) -> ToolDefinition | None:
    """按稳定 ID 返回内置工具定义。"""
    return _TOOLS_BY_ID.get(str(tool_id or ""))
