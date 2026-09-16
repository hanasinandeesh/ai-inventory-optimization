"""
Test No Hardcoded Business Logic.
Scans source files to verify no hardcoded seed SKUs, DC codes, or scenario magic numbers
exist in application logic.
"""

from pathlib import Path


def test_no_hardcoded_seed_constants_in_application_logic() -> None:
    """
    Scans source files in app/domain, app/services, app/api to ensure no hardcoded seed data
    or special cases exist in core application code.
    """
    forbidden_tokens = [
        "SKU-8842",
        "DC-CHI",
        "DC-IND",
        "DC-DAL",
    ]

    target_dirs = [
        Path("app/domain"),
        Path("app/services"),
        Path("app/api"),
    ]

    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        for py_file in target_dir.glob("**/*.py"):
            content = py_file.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                assert token not in content, (
                    f"Forbidden hardcoded token '{token}' found in {py_file}"
                )
