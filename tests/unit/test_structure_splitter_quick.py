"""Quick smoke test for StructureSplitter."""
from src.core.settings import load_settings
from src.libs.splitter.splitter_factory import SplitterFactory


def main() -> None:
    settings = load_settings("config/settings.yaml")
    splitter = SplitterFactory.create(settings)
    print("Splitter type:", type(splitter).__name__)

    test_md = (
        "# 第一章 总则\n\n"
        "本规定适用于所有部门的差旅报销流程。\n\n"
        "## 1.1 适用范围\n\n"
        "适用于公司全体员工，包括正式员工和实习生。出差前需填写出差申请表。\n\n"
        "## 1.2 报销标准\n\n"
        "| 级别 | 交通 | 住宿 | 餐饮 |\n"
        "|------|------|------|------|\n"
        "| 经理 | 商务舱 | 500元/晚 | 200元/天 |\n"
        "| 员工 | 经济舱 | 300元/晚 | 150元/天 |\n\n"
        "## 1.3 注意事项\n\n"
        "所有发票必须在出差结束后5个工作日内提交。逾期不予报销。\n\n"
        "```python\n"
        "def calculate_reimbursement(level, days):\n"
        '    rates = {"manager": 700, "employee": 450}\n'
        "    return rates.get(level, 0) * days\n"
        "```\n\n"
        "# 第二章 审批流程\n\n"
        "审批流程分为三级：部门经理、财务部、总经理。\n"
    )

    chunks = splitter.split_text(test_md)
    print(f"Chunks: {len(chunks)}")
    for i, c in enumerate(chunks):
        preview = c[:80].replace("\n", " ")
        print(f"  [{i}] len={len(c):4d}  {preview}...")


if __name__ == "__main__":
    main()
