import pytest

from tests._fakes import build_sample_result


@pytest.fixture
def sample_result():
    """115-1 的 TermResult（FakeClient 回放 csie fixture）。函式範疇，避免跨測試 mutate。"""
    return build_sample_result("115-1")
