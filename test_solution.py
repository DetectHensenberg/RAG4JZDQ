"""方案助手核心模块测试脚本.

验证：
1. solution_db — CRUD 操作
2. template_parser — Word 标题提取
3. requirement_parser — 文本格式推断
4. outline_generator — 默认大纲生成
5. solution_exporter — Word 导出
6. API Router — 模块导入
"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(__file__))

def test_solution_db():
    """测试会话 CRUD."""
    print("=" * 60)
    print("T1: 测试 solution_db.py")
    print("=" * 60)

    from src.solution.solution_db import (
        SolutionSession,
        create_session,
        get_session,
        update_session,
        delete_session,
        list_sessions,
    )

    # Create
    session = SolutionSession(
        project_name="测试项目",
        project_type="系统集成",
        source_text="这是一段测试需求文本",
        requirements=[{"id": "REQ-001", "title": "测试需求"}],
        collection="default",
    )
    sid = create_session(session)
    print(f"  ✅ create_session → id={sid}")
    assert sid > 0

    # Read
    s = get_session(sid)
    assert s is not None
    assert s.project_name == "测试项目"
    assert len(s.requirements) == 1
    print(f"  ✅ get_session → project_name={s.project_name}")

    # Update
    s.outline = [{"id": "SEC-001", "title": "项目概述", "level": 1}]
    s.status = "outlining"
    ok = update_session(s)
    assert ok
    s2 = get_session(sid)
    assert s2 is not None
    assert s2.status == "outlining"
    assert len(s2.outline) == 1
    print(f"  ✅ update_session → status={s2.status}, outline len={len(s2.outline)}")

    # List
    result = list_sessions(page=1, page_size=10)
    assert result["total"] >= 1
    print(f"  ✅ list_sessions → total={result['total']}")

    # to_dict
    d = s2.to_dict()
    assert d["project_name"] == "测试项目"
    print(f"  ✅ to_dict → keys={list(d.keys())[:5]}...")

    # Delete
    ok = delete_session(sid)
    assert ok
    assert get_session(sid) is None
    print(f"  ✅ delete_session → deleted")

    print("  🎉 T1 全部通过\n")


def test_template_parser():
    """测试模板解析（文本格式推断）."""
    print("=" * 60)
    print("T2.5: 测试 template_parser.py")
    print("=" * 60)

    from src.solution.template_parser import _detect_heading_level_from_text

    cases = [
        ("第一章 项目概述", 1),
        ("一、项目背景", 1),
        ("（一）建设目标", 2),
        ("1. 系统架构", 1),
        ("1.1 技术选型", 2),
        ("1.1.1 数据库选型", 3),
        ("普通正文内容", None),
        ("", None),
    ]

    for text, expected in cases:
        result = _detect_heading_level_from_text(text)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{text}' → level={result} (expected={expected})")
        assert result == expected, f"Failed: '{text}' got {result}, expected {expected}"

    print("  🎉 T2.5 全部通过\n")


def test_requirement_parser_json():
    """测试 LLM JSON 解析函数."""
    print("=" * 60)
    print("T2: 测试 requirement_parser.py (JSON 解析)")
    print("=" * 60)

    from src.solution.requirement_parser import _parse_llm_json

    # 标准 JSON
    r1 = _parse_llm_json('[{"id":"REQ-001","title":"测试"}]')
    assert len(r1) == 1
    print(f"  ✅ 标准 JSON → {len(r1)} 条")

    # 带代码块
    r2 = _parse_llm_json('```json\n[{"id":"REQ-001"}]\n```')
    assert len(r2) == 1
    print(f"  ✅ 代码块包裹 → {len(r2)} 条")

    # 带前后杂文
    r3 = _parse_llm_json('以下是需求：\n[{"id":"REQ-001"}]\n以上就是全部。')
    assert len(r3) == 1
    print(f"  ✅ 带杂文 → {len(r3)} 条")

    # 空/无效
    r4 = _parse_llm_json("无法解析的文本")
    assert len(r4) == 0
    print(f"  ✅ 无效文本 → {len(r4)} 条")

    print("  🎉 T2 全部通过\n")


def test_outline_generator_default():
    """测试默认大纲生成."""
    print("=" * 60)
    print("T3: 测试 outline_generator.py (默认大纲)")
    print("=" * 60)

    from src.solution.outline_generator import generate_default_outline

    reqs = [
        {"id": "REQ-001", "category": "functional", "title": "用户登录"},
        {"id": "REQ-002", "category": "non_functional", "title": "系统性能"},
    ]

    outline = generate_default_outline(reqs)
    assert len(outline) >= 10
    print(f"  ✅ 默认大纲 → {len(outline)} 个章节")

    # 检查需求分配
    func_section = [s for s in outline if s.get("title") == "功能需求"][0]
    assert "REQ-001" in func_section.get("requirement_ids", [])
    print(f"  ✅ REQ-001 分配到'功能需求'章节")

    nf_section = [s for s in outline if s.get("title") == "非功能需求"][0]
    assert "REQ-002" in nf_section.get("requirement_ids", [])
    print(f"  ✅ REQ-002 分配到'非功能需求'章节")

    print("  🎉 T3 全部通过\n")


def test_solution_exporter():
    """测试 Word 导出."""
    print("=" * 60)
    print("T5: 测试 solution_exporter.py")
    print("=" * 60)

    import tempfile
    from src.solution.solution_exporter import export_to_docx

    outline = [
        {"id": "SEC-001", "title": "项目概述", "level": 1},
        {"id": "SEC-002", "title": "项目背景", "level": 2},
        {"id": "SEC-003", "title": "系统设计", "level": 1},
    ]
    content = {
        "SEC-002": "本项目旨在建设**智慧城市**管理平台。\n\n- 功能一\n- 功能二\n\n1. 步骤一\n2. 步骤二",
        "SEC-003": "系统采用微服务架构，技术栈包括：\n\n```python\ndef hello():\n    print('hello')\n```",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test_solution.docx")
        result = export_to_docx(
            outline=outline,
            content=content,
            output_path=out_path,
            project_name="智慧城市管理平台",
            project_type="系统集成",
        )
        assert os.path.exists(result)
        size = os.path.getsize(result)
        print(f"  ✅ 导出成功: {result}")
        print(f"  ✅ 文件大小: {size} bytes")
        assert size > 1000, f"文件太小({size}bytes)，可能导出异常"

    print("  🎉 T5 全部通过\n")


def test_api_router_import():
    """测试 API Router 模块导入."""
    print("=" * 60)
    print("T6: 测试 api/routers/solution.py 导入")
    print("=" * 60)

    from api.routers.solution import router
    routes = [r.path for r in router.routes]
    print(f"  ✅ Router 导入成功, {len(routes)} 个路由")
    print(f"  ✅ 路由列表: {routes}")

    expected_paths = ["/parse", "/upload-template", "/outline", "/generate", "/export", "/sessions"]
    for p in expected_paths:
        found = any(p in r for r in routes)
        status = "✅" if found else "❌"
        print(f"  {status} {p}")
        assert found, f"缺少路由: {p}"

    print("  🎉 T6 全部通过\n")


if __name__ == "__main__":
    print("\n🚀 方案助手核心模块测试\n")
    passed = 0
    failed = 0

    tests = [
        test_solution_db,
        test_template_parser,
        test_requirement_parser_json,
        test_outline_generator_default,
        test_solution_exporter,
        test_api_router_import,
    ]

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ 测试失败: {e}\n")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 项")
    print("=" * 60)
