import unittest

from app.sites.cookiecloud import cookiecloud_site_candidates


class CookieCloudDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.catalog = [{"id": "fixture", "name": "测试站", "domain": "https://pt.example.org/",
                         "aliases": ["https://old.example.net/"]}]

    def discover(self, cookies, sites=None, catalog=None):
        return cookiecloud_site_candidates(self.catalog if catalog is None else catalog, cookies, sites or [])

    def test_exact_cookie_host_discovers_known_site_and_ignores_unknown_domains(self):
        result = self.discover({
            "example.org": [{"domain": ".pt.example.org", "name": "session", "value": "known"}],
            "unrelated.example": [{"name": "session", "value": "unknown"}],
        })
        self.assertEqual([{"name": "测试站", "signurl": "https://pt.example.org/"}], result)

    def test_alias_retains_its_address_and_both_alias_fields_are_supported(self):
        self.catalog[0]["domains"] = "https://other.example.net/"
        result = self.discover({
            "old.example.net": [{"name": "session", "value": "old"}],
            "other.example.net": [{"name": "session", "value": "other"}],
        })
        self.assertEqual([
            {"name": "测试站", "signurl": "https://old.example.net/"},
            {"name": "测试站", "signurl": "https://other.example.net/"},
        ], result)

    def test_existing_alias_or_name_skips_entire_catalog_entry(self):
        contents = {"pt.example.org": [{"name": "session", "value": "new"}]}
        for site in ({"name": "测试站"}, {"name": "custom", "signurl": "https://old.example.net/signin"},
                     {"rssurl": "https://www.old.example.net/rss?passkey=secret"},
                     {"strict_url": "https://PT.EXAMPLE.ORG:443/"}):
            with self.subTest(site=site):
                self.assertEqual([], self.discover(contents, [site]))

    def test_parent_domain_discovers_unique_known_subdomain(self):
        self.assertEqual([{"name": "测试站", "signurl": "https://pt.example.org/"}], self.discover({
            "example.org": [{"domain": ".example.org", "name": "session", "value": "shared"}],
        }))

    def test_host_only_parent_domain_does_not_discover_subdomain(self):
        self.assertEqual([], self.discover({
            "example.org": [{"domain": "example.org", "hostOnly": True, "name": "session", "value": "root"}],
        }))

    def test_ambiguous_parent_does_not_add_sibling_sites(self):
        self.catalog.append({"id": "sibling", "name": "同父域站点", "domain": "https://other.example.org/"})
        for existing in ([], [{"name": "同父域站点", "signurl": "https://other.example.org/"}]):
            with self.subTest(existing=existing):
                self.assertEqual([], self.discover({
                    "example.org": [{"domain": ".example.org", "name": "session", "value": "shared"}],
                }, existing))

    def test_explicit_bucket_limits_parent_cookie_to_observed_sibling(self):
        self.catalog.append({"id": "sibling", "name": "同父域站点", "domain": "https://other.example.org/"})
        self.assertEqual([{"name": "测试站", "signurl": "https://pt.example.org/"}], self.discover({
            "pt.example.org": [{"domain": ".example.org", "name": "session", "value": "shared"}],
        }))

    def test_unknown_sibling_does_not_infer_catalog_site_from_parent_cookie(self):
        self.assertEqual([], self.discover({
            "unrelated.example.org": [{"domain": ".example.org", "name": "session", "value": "shared"}],
        }))

    def test_bucket_cannot_override_host_only_cookie_scope(self):
        self.assertEqual([], self.discover({
            "pt.example.org": [{"domain": "example.org", "hostOnly": True, "name": "session", "value": "root"}],
        }))

    def test_www_equivalent_uses_observed_host_including_host_only_cookie(self):
        catalog = [{"id": "fixture", "name": "测试站", "domain": "https://www.example.org/forum/"}]
        result = self.discover({"example.org": [
            {"domain": "example.org", "hostOnly": True, "name": "session", "value": "root"},
        ]}, catalog=catalog)
        self.assertEqual([{"name": "测试站", "signurl": "https://example.org/forum/"}], result)

    def test_direct_alias_precedes_inferred_primary_address(self):
        self.assertEqual([
            {"name": "测试站", "signurl": "https://old.example.net/"},
            {"name": "测试站", "signurl": "https://pt.example.org/"},
        ], self.discover({
            "example.org": [{"domain": ".example.org", "name": "session", "value": "parent"}],
            "old.example.net": [{"domain": "old.example.net", "name": "session", "value": "alias"}],
        }))

    def test_repeated_cookies_do_not_duplicate_candidate_and_paths_are_preserved(self):
        self.catalog[0]["domain"] = "https://PT.EXAMPLE.ORG:8443/forum/"
        result = self.discover({"pt.example.org": [
            {"name": "session", "value": "one"}, {"name": "uid", "value": "two"},
        ]})
        self.assertEqual([{"name": "测试站", "signurl": "https://pt.example.org:8443/forum/"}], result)

    def test_empty_malformed_or_invalid_catalog_entries_are_ignored(self):
        catalog = [None, {}, {"name": "坏地址", "domain": "file:///tmp/site"},
                   {"name": "无主机", "domain": "https://"},
                   {"name": "凭据地址", "domain": "https://user:secret@pt.example.org/"}]
        self.assertEqual([], self.discover({"pt.example.org": [{"name": "session", "value": "x"}]},
                                          catalog=catalog))
        for contents in ({}, {"pt.example.org": []}, {"pt.example.org": [None]}, {"pt.example.org": "bad"}):
            with self.subTest(contents=contents):
                self.assertEqual([], self.discover(contents))

    def test_top_level_domain_cookie_is_not_used_to_infer_a_site(self):
        self.assertEqual([], self.discover({"org": [{"name": "session", "value": "bad"}]}))


if __name__ == "__main__":
    unittest.main()
