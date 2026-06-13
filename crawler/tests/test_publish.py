from infra.publish import cache_control_for, plan_uploads, quality_gate, r2_key


def test_r2_key_prefix():
    assert r2_key("v1/manifest.json") == "course/v1/manifest.json"
    assert r2_key("v1/terms/115-1/catalog.json") == "course/v1/terms/115-1/catalog.json"


def test_cache_control():
    assert "max-age=300" in cache_control_for("v1/manifest.json")
    assert "max-age=3600" in cache_control_for("v1/terms/115-1/catalog.json")
    assert "max-age=3600" in cache_control_for("v1/terms/115-1/classes.json")
    assert "max-age=300" in cache_control_for("v1/terms/115-1/enrollment.json")


def test_quality_gate():
    assert quality_gate(current=2440, previous=2450, min_ratio=0.95)[0] is True
    assert quality_gate(current=100, previous=200, min_ratio=0.95)[0] is False   # 掉 50%
    assert quality_gate(current=0, previous=0, min_ratio=0.95)[0] is False        # 0 課必擋
    assert quality_gate(current=2440, previous=0, min_ratio=0.95)[0] is True      # 首次（無基準）放行


def test_plan_uploads_manifest_last():
    files = [
        "v1/terms/115-1/catalog.json",
        "v1/manifest.json",
        "v1/terms/115-1/enrollment.json",
    ]
    plan = plan_uploads(files)
    assert plan[-1] == "v1/manifest.json"           # manifest 最後（原子性）
    assert set(plan) == set(files)
