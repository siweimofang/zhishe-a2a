"""Smoke test - 验证 Mavis 写权限授权是否生效。
如果这个文件能成功创建,说明用户已经在 Mavis 弹窗中点击了"始终允许"。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_FILE = ROOT / "tests" / ".write_permission_verified"


def verify_write_permission() -> bool:
    """在 tests/ 下创建一个标记文件,验证对 D:/zhishe-a2a 的写权限。"""
    TEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_FILE.write_text(
        "Mavis write permission: GRANTED (always allow)\n",
        encoding="utf-8",
    )
    return TEST_FILE.exists()


if __name__ == "__main__":
    ok = verify_write_permission()
    print(f"write permission verified: {ok}")
    print(f"marker file: {TEST_FILE}")
