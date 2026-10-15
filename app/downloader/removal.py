import re


def matches_pattern(pattern, value):
    return bool(re.findall(pattern, value, re.I))


class TorrentRemovalRules:
    """共享删种阈值、标签交集和辅种扩展；客户端负责字段与状态适配。"""

    def __init__(self, config):
        self._ratio = config.get("ratio")
        self._seeding_time = config.get("seeding_time")
        size = config.get("size")
        self._size = size
        self._min_size = size[0] * 1024 ** 3 if size else 0
        self._max_size = size[-1] * 1024 ** 3 if size else 0
        self._upload_avs = config.get("upload_avs")
        self.required_tags = set(config.get("filter_tags") or [])
        self._samedata = config.get("samedata")

    def has_required_tags(self, tags):
        return self.required_tags.issubset(tags)

    def matches_limits(self, *, ratio, seeding_time, size, uploaded):
        upload_avs = uploaded / seeding_time if seeding_time else 0
        # 沿用严格边界；配置中的 0 仍表示不启用该规则。
        if self._ratio and ratio <= self._ratio:
            return False
        if self._seeding_time and seeding_time <= self._seeding_time * 3600:
            return False
        if self._size and (size >= self._max_size or size <= self._min_size):
            return False
        if self._upload_avs and upload_avs >= self._upload_avs * 1024:
            return False
        return True

    def select(self, torrents, *, matches, tags, identity, describe):
        """返回原有删种字典；identity 提供 (id, name, size)，describe 延迟读取站点。"""
        selected = []
        selected_ids = set()
        for torrent in torrents:
            if matches(torrent):
                item = describe(torrent)
                selected.append(item)
                selected_ids.add(item["id"])

        if not self._samedata or not selected:
            return selected

        expanded = []
        for item in selected:
            for torrent in torrents:
                # 辅种只复核标签和同名同大小，不重新应用阈值、路径或客户端状态。
                if self.required_tags and not self.has_required_tags(tags(torrent)):
                    continue
                torrent_id, name, size = identity(torrent)
                if name == item["name"] and size == item["size"] and torrent_id not in selected_ids:
                    expanded.append(describe(torrent, expanded=True))
        # 保留扩展优先的顺序及每个基础命中项各自的扩展结果。
        return expanded + selected
