from models import ClassKind, ClassRef
from ntut_catalog.classes_builder import (
    build_class_directory,
    classify_kind,
    resolve_class_ref,
)


def test_classify_kind_regular():
    # 應英系正規班「英文一~四 / 英文所」不可誤標 pool
    for name in ["資工二", "資工所", "機械三甲", "電機碩一", "EMBA",
                 "英文一", "英文四", "英文所", "職英文所"]:
        assert classify_kind(name) == ClassKind.regular, name


def test_classify_kind_pool():
    for name in ["博雅課程(三)", "職博雅課程(一)", "體育專項(二)", "大一英文(五)",
                 "大二英文(一)", "大二專業英文(四)", "共同英文(三)", "體育興趣(七)",
                 "專業職場英文銜接計畫"]:
        assert classify_kind(name) == ClassKind.pool, name


def test_build_class_directory_merges_sources():
    subj_classes = {("59", "資工系"): [("3032", "資工二"), ("3163", "資工所")]}
    # 課程列出現、但 Subj -3 沒列的班級（如博雅 pool 班）
    course_classes = [("9001", "博雅課程(三)"), ("3032", "資工二")]
    directory = build_class_directory("114-1", subj_classes, course_classes)
    assert directory.term_key == "114-1"
    by_code = {c.code: c for c in directory.classes}
    assert by_code["3032"].kind == ClassKind.regular
    assert by_code["3032"].unit_code == "59"
    assert by_code["9001"].kind == ClassKind.pool
    assert by_code["9001"].unit_code is None     # 不知道就 None，不猜
    assert len(directory.classes) == 3           # 去重


def test_grade_extraction():
    subj = {("59", "資工系"): [("3032", "資工二"), ("3163", "資工所"), ("2798", "資工四")]}
    d = build_class_directory("114-1", subj, [])
    by_code = {c.code: c for c in d.classes}
    assert by_code["3032"].grade == 2
    assert by_code["2798"].grade == 4
    assert by_code["3163"].grade is None         # 研究所單一碼不分年級


def test_resolve_class_ref_hits_lookup():
    pool = ClassRef(code="9001", name="博雅課程(三)", kind=ClassKind.pool,
                    unit_code="14", grade=None)
    ref = resolve_class_ref("9001", "博雅課程(三)", {"9001": pool})
    assert ref is pool                            # 直接採用 directory 物件（單一真相）


def test_resolve_class_ref_fallback():
    ref = resolve_class_ref("9999", "博雅課程(五)", {})
    assert ref.code == "9999"
    assert ref.kind == ClassKind.pool             # 防呆：依名稱分類
    assert ref.unit_code is None
