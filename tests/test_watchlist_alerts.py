import unittest

from src.services.watchlist_alerts import expand_symbol_targets


class WatchlistAlertsTestCase(unittest.TestCase):
    def test_watchlist_expansion_refreshes_stock_list(self) -> None:
        class Config:
            stock_list = ["600519", "600519", "600519"]

            def __init__(self):
                self.refreshed = False

            def refresh_stock_list(self):
                self.refreshed = True
                self.stock_list = ["000001", "000001", "000002"]

        config = Config()
        targets, overflow = expand_symbol_targets(
            target_scope="watchlist",
            target="default",
            config=config,
        )

        self.assertTrue(config.refreshed)
        self.assertEqual([item.symbol for item in targets], ["000001", "000002"])
        self.assertEqual(overflow, 0)
