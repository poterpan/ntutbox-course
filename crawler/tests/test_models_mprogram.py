from models import SCHEMA_VERSION, MicroProgram, MicroProgramCourse, MicroProgramDirectory


def test_schema_version_bumped():
    """v3：Syllabus 的 flex_learning/extra 從 dict 換成有序的 label/value 陣列
    （破壞性型別變更，issue #96）。消費端讀到比自己認識的更新的版本時應降級容忍，
    不是整包拒收。"""
    assert SCHEMA_VERSION == 3


def test_microprogram_course_fields():
    c = MicroProgramCourse(course_code="1401041", name_zh="物理", credits=3.0,
                           category="基礎", category_raw="基礎", online=False)
    assert c.category == "基礎" and c.online is False


def test_microprogram_new_fields_default():
    p = MicroProgram(code="AV2", name="面板微學程")
    assert p.courses == [] and p.rules_text is None


def test_directory_roundtrip():
    d = MicroProgramDirectory(term_key="115-1", programs=[MicroProgram(
        code="AV2", name="面板微學程", offering_ids=["241001"],
        courses=[MicroProgramCourse(course_code="1401041", name_zh="物理",
                                    credits=3.0, category="核心", category_raw="核e", online=True)],
        rules_text="一、…")])
    j = MicroProgramDirectory.model_validate_json(d.model_dump_json())
    assert j.programs[0].courses[0].online is True
