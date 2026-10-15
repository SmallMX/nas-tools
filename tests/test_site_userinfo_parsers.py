import unittest
from urllib.parse import parse_qsl, urlsplit

from app.sites.siteuserinfo.discuz import DiscuzUserInfo
from app.sites.siteuserinfo.nexus_php import NexusPhpSiteUserInfo


class SiteUserInfoParsersTest(unittest.TestCase):
    UUID = "01234567-89ab-cdef-0123-456789abcdef"

    @staticmethod
    def parser(parser_class):
        return parser_class("Test", "https://tracker.example/", "", "")

    def test_discuz_ratio_uses_label_in_mixed_nested_metrics(self):
        parser = self.parser(DiscuzUserInfo)
        parser._parse_user_detail_info("""
            <ul>
              <li><em>PT</em>上传量 (12.0 GB) <span>分享率</span>：<b>（1,234.50）</b></li>
              <li><em>积分</em>678.9</li>
            </ul>
        """)

        self.assertEqual(1234.5, parser.ratio)
        self.assertEqual(678.9, parser.bonus)

    def test_discuz_ratio_does_not_overwrite_bonus(self):
        for label in ("分享率 (2.5)", "分享率：2.5", "分享<span>率</span><b>2.5</b>"):
            with self.subTest(label=label):
                parser = self.parser(DiscuzUserInfo)
                parser.bonus = 17
                parser._parse_user_detail_info(f"<ul><li>{label}</li></ul>")
                self.assertEqual(2.5, parser.ratio)
                self.assertEqual(17, parser.bonus)

    def test_discuz_zero_and_missing_ratio(self):
        parser = self.parser(DiscuzUserInfo)
        parser._parse_user_detail_info("<ul><li>分享率 <b>(0.00)</b></li></ul>")
        self.assertEqual(0.0, parser.ratio)
        parser._parse_user_detail_info("<ul><li>上传量 (99)</li></ul>")
        self.assertEqual(0.0, parser.ratio)

    def test_nexus_numeric_and_uuid_user_detail_links(self):
        for user_id, detail_key, seeding_key in (
                ("123", "id", "userid"),
                (self.UUID, "uuid", "useruuid"),
                (self.UUID.upper(), "uuid", "useruuid")):
            with self.subTest(user_id=user_id):
                parser = self.parser(NexusPhpSiteUserInfo)
                parser._parse_site_page(f'<a href="userdetails.php?{detail_key}={user_id}">User</a>')
                self.assertEqual(user_id, parser.userid)
                self.assertEqual(f"userdetails.php?{detail_key}={user_id}", parser._user_detail_page)
                self.assertEqual(
                    {seeding_key: user_id, "type": "seeding"},
                    dict(parse_qsl(urlsplit(parser._torrent_seeding_page).query)),
                )

    def test_nexus_invalid_user_id_is_not_truncated_to_a_number(self):
        parser = self.parser(NexusPhpSiteUserInfo)
        parser._parse_site_page('<a href="userdetails.php?id=123invalid">User</a>')

        self.assertIsNone(parser.userid)
        self.assertIsNone(parser._torrent_seeding_page)

    def test_nexus_next_page_adds_named_parameters_and_keeps_fragment(self):
        for user_id, user_key in (("2", "userid"), (self.UUID, "useruuid")):
            with self.subTest(user_id=user_id):
                parser = self.parser(NexusPhpSiteUserInfo)
                parser.userid = user_id
                result = parser._parse_user_torrent_seeding_info(
                    '<html><a href="getusertorrentlistajax.php?page=2&amp;filter=a&amp;filter=b#list">下一页</a></html>'
                )
                parsed = urlsplit(result)
                query = parse_qsl(parsed.query)
                self.assertEqual("getusertorrentlistajax.php", parsed.path)
                self.assertEqual("list", parsed.fragment)
                self.assertIn((user_key, user_id), query)
                self.assertIn(("type", "seeding"), query)
                self.assertEqual(["a", "b"], [value for key, value in query if key == "filter"])

    def test_nexus_next_page_without_query_uses_question_mark(self):
        parser = self.parser(NexusPhpSiteUserInfo)
        parser.userid = "42"

        result = parser._fixup_next_page_url("getusertorrentlistajax.php#list")

        self.assertEqual("getusertorrentlistajax.php?userid=42&type=seeding#list", result)

    def test_nexus_next_page_keeps_existing_user_identifiers(self):
        for user_key, user_id in (("userid", "42"), ("useruuid", self.UUID)):
            with self.subTest(user_key=user_key):
                parser = self.parser(NexusPhpSiteUserInfo)
                result = parser._fixup_next_page_url(f"?page=2&{user_key}={user_id}&type=seeding")
                self.assertEqual(
                    [("page", "2"), (user_key, user_id), ("type", "seeding")],
                    parse_qsl(urlsplit(result).query),
                )

    def test_nexus_next_page_repairs_empty_parameters(self):
        parser = self.parser(NexusPhpSiteUserInfo)
        parser.userid = self.UUID

        result = parser._fixup_next_page_url("?page=2&userid=&type=")

        self.assertEqual(
            {"page": "2", "useruuid": self.UUID, "type": "seeding"},
            dict(parse_qsl(urlsplit(result).query)),
        )

    def test_nexus_next_page_stops_without_user_identifier(self):
        parser = self.parser(NexusPhpSiteUserInfo)
        self.assertIsNone(parser._fixup_next_page_url("?page=2"))
        self.assertIsNone(parser._fixup_next_page_url(""))

    def test_nexus_javascript_links_support_numeric_and_uuid_ids(self):
        for user_id, user_key in (("42", "userid"), (self.UUID, "useruuid")):
            for quote in ("'", "&quot;"):
                with self.subTest(user_id=user_id, quote=quote):
                    parser = self.parser(NexusPhpSiteUserInfo)
                    parser._parse_site_page('<a href="userdetails">User</a>')
                    parser._parse_user_detail_info(
                        f'<a href="javascript:getusertorrentlistajax({quote}{user_id}{quote}, \'seeding\')">做种</a>'
                    )
                    self.assertEqual(user_id, parser.userid)
                    self.assertEqual(
                        {user_key: user_id, "type": "seeding"},
                        dict(parse_qsl(urlsplit(parser._torrent_seeding_page).query)),
                    )

    def test_nexus_csrf_request_uses_matching_identifier_parameter(self):
        for user_id, user_key in (("42", "userid"), (self.UUID, "useruuid")):
            with self.subTest(user_id=user_id):
                parser = self.parser(NexusPhpSiteUserInfo)
                parser._parse_site_page('<a href="userdetails">User</a>')
                parser._parse_user_detail_info(
                    '<html><head><meta name="x-csrf" content="csrf-token"></head><body>'
                    f'<a href="javascript: getusertorrentlistajax(\'{user_id}\', \'seeding\')">做种</a>'
                    '</body></html>'
                )
                self.assertEqual("ajax_getusertorrentlist.php", parser._torrent_seeding_page)
                self.assertEqual(
                    {user_key: user_id, "type": "seeding", "csrf": "csrf-token"},
                    parser._torrent_seeding_params,
                )


if __name__ == "__main__":
    unittest.main()
