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
