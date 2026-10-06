import sys
from pathlib import Path

import pytest

# 讓測試能 import 倉庫根目錄的 infra/ 套件（publish/redline_scan）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests._fakes import build_sample_result


def pytest_addoption(parser):
    parser.addoption(
        "--update-contract-fixtures", action="store_true", default=False,
        help="重寫 fixtures/contract/*.json（刻意改契約時才用；見 test_contract_fixtures.py）",
    )


@pytest.fixture
def sample_result():
    """115-1 的 TermResult（FakeClient 回放 csie fixture）。函式範疇，避免跨測試 mutate。"""
    return build_sample_result("115-1")


@pytest.fixture(autouse=True)
def _no_campus_network(monkeypatch):
    """daily 跑全部資料集時會帶到 campus_gis：預設 client 換成假的，測試永不連 CDN。"""
    from ntut_catalog import registry
    from tests._fakes import FakeCampusClient
    monkeypatch.setattr(registry, "_default_campus_client", FakeCampusClient)
