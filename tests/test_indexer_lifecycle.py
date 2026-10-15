import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.indexer import Indexer


class IndexerLifecycleTest(unittest.TestCase):
    def test_failed_reload_disables_stale_client_and_can_recover(self):
        indexer = Indexer()
        error = RuntimeError("indexer initialization failed")
        recovered_client = Mock()
        recovered_client.get_indexers.return_value = [SimpleNamespace(id="example", name="Example")]

        with patch.object(indexer, "_client", Mock()), \
                patch.object(indexer, "progress", Mock()), \
                patch("app.indexer.indexer.ProgressHelper"), \
                patch("app.indexer.indexer.ExceptionUtils.exception_traceback") as report, \
                patch("app.indexer.indexer.BuiltinIndexer", side_effect=[error, recovered_client]):
            indexer.init_config()

            self.assertIsNone(indexer.get_client())
            self.assertEqual([], indexer.get_indexers())
            self.assertEqual([], indexer.search_by_keyword("Example", {}))
            report.assert_called_once_with(error)

            indexer.init_config()

            self.assertEqual([{"id": "example", "name": "Example"}], indexer.get_indexer_dict())


if __name__ == "__main__":
    unittest.main()
