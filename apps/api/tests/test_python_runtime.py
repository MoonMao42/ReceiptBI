"""Security-contract tests for the maintained Python sandbox helpers."""

import pytest

from app.services.python_runtime import PythonSecurityAnalyzer, validate_python_code


@pytest.mark.parametrize(
    "code",
    [
        "import pandas as pd\nframe.head()",
        "import matplotlib.pyplot as plt\nplt.show()",
        "import numpy as np\nnp.array([1, 2, 3]).mean()",
        "print('hello')",
    ],
)
def test_python_security_analyzer_accepts_analysis_code(code: str) -> None:
    assert PythonSecurityAnalyzer.analyze(code) == (True, [])


@pytest.mark.parametrize(
    "code",
    [
        "import os\nos.system('whoami')",
        "from subprocess import run",
        "open('report.txt', 'w')",
        "exec('print(1)')",
        "func.__globals__",
    ],
)
def test_python_security_analyzer_rejects_host_access(code: str) -> None:
    is_safe, violations = PythonSecurityAnalyzer.analyze(code)
    assert is_safe is False
    assert violations


def test_validate_python_code_reports_syntax_errors_without_executing() -> None:
    is_safe, error = validate_python_code("for item in")
    assert is_safe is False
    assert error and "语法错误" in error
