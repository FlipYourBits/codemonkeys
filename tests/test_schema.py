from typing import Literal
from pydantic import BaseModel, Field
import pytest
from agentpipe.schema import generate_output_instructions, parse_output


class SimpleModel(BaseModel):
    name: str = Field(examples=["alice"])
    count: int = Field(examples=[7])


class SeverityModel(BaseModel):
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: bug that will cause incorrect behavior in production. MEDIUM: latent bug under specific conditions. LOW: minor concern worth surfacing but not blocking"
    )


class Item(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])


class NestedModel(BaseModel):
    findings: list[Item]


class DictModel(BaseModel):
    stats: dict = Field(examples=[{"total": 5}])


class NoExamplesModel(BaseModel):
    label: str
    score: float
    active: bool


class TwoLiteralsModel(BaseModel):
    status: Literal["PASS", "FAIL"] = Field(
        description="PASS: all checks succeeded. FAIL: one or more checks failed"
    )
    priority: Literal["HIGH", "LOW"] = Field(
        description="HIGH: urgent attention needed. LOW: can be addressed later"
    )


def test_simple_model_has_json_example():
    result = generate_output_instructions(SimpleModel)
    assert "## Output" in result
    assert "```json" in result
    assert '"alice"' in result
    assert "7" in result


def test_literal_field_renders_allowed_values():
    result = generate_output_instructions(SeverityModel)
    assert "HIGH" in result
    assert "MEDIUM" in result
    assert "LOW" in result
    assert "bug that will cause incorrect behavior in production" in result
    assert "latent bug under specific conditions" in result
    assert "minor concern worth surfacing but not blocking" in result


def test_nested_model_renders_example():
    result = generate_output_instructions(NestedModel)
    assert "path/to/file.py" in result
    assert "42" in result


def test_dict_field_with_example():
    result = generate_output_instructions(DictModel)
    assert '"total"' in result
    assert "5" in result


def test_field_without_examples_uses_type_default():
    result = generate_output_instructions(NoExamplesModel)
    assert '"label"' in result
    assert '"score"' in result
    assert '"active"' in result
    # defaults: str -> "...", float -> 0.0, bool -> true
    assert '"..."' in result
    assert "0.0" in result
    assert "true" in result


def test_multiple_literal_fields_each_rendered():
    result = generate_output_instructions(TwoLiteralsModel)
    assert "PASS" in result
    assert "FAIL" in result
    assert "all checks succeeded" in result
    assert "one or more checks failed" in result
    assert "urgent attention needed" in result
    assert "can be addressed later" in result


# --- parse_output tests ---

class ValueModel(BaseModel):
    value: int


def test_parses_fenced_json():
    text = '```json\n{"value": 42}\n```'
    result = parse_output(ValueModel, text)
    assert isinstance(result, ValueModel)
    assert result.value == 42


def test_parses_raw_json():
    result = parse_output(ValueModel, '{"value": 42}')
    assert result.value == 42


def test_parses_nested_model():
    text = '```json\n{"findings": [{"file": "foo.py", "line": 10}]}\n```'
    result = parse_output(NestedModel, text)
    assert isinstance(result, NestedModel)
    assert result.findings[0].file == "foo.py"
    assert result.findings[0].line == 10


def test_raises_on_no_json():
    with pytest.raises(ValueError, match="No JSON"):
        parse_output(ValueModel, "plain text with no json here")


def test_raises_on_invalid_json():
    with pytest.raises(ValueError):
        parse_output(ValueModel, "```json\n{invalid}\n```")


def test_raises_on_validation_error():
    with pytest.raises(ValueError):
        parse_output(ValueModel, '{"value": "not_an_int"}')


def test_handles_text_before_and_after_json():
    text = "Some preamble text.\n```json\n{\"value\": 7}\n```\nSome trailing text."
    result = parse_output(ValueModel, text)
    assert result.value == 7


class TestCodeReviewModels:
    def test_code_review_output_validates(self):
        from agentpipe.nodes.python_code_review import CodeReviewOutput
        data = {
            "findings": [{
                "file": "a.py", "line": 42, "severity": "HIGH",
                "category": "logic_error", "source": "python_code_review",
                "description": "Bug.", "recommendation": "Fix it.",
                "confidence": "high",
            }],
            "summary": {"files_reviewed": 1, "high": 1, "medium": 0, "low": 0},
        }
        output = CodeReviewOutput.model_validate(data)
        assert len(output.findings) == 1
        assert output.findings[0].severity == "HIGH"

    def test_code_review_node_has_output_instructions(self):
        from agentpipe.nodes.python_code_review import PythonCodeReview
        node = PythonCodeReview()
        assert "## Output" in node.system_prompt
        assert "severity" in node.system_prompt.lower()


class TestSecurityAuditModels:
    def test_security_audit_output_validates(self):
        from agentpipe.nodes.python_security_audit import SecurityAuditOutput
        data = {
            "findings": [{
                "file": "a.py", "line": 10, "severity": "HIGH",
                "category": "command_injection", "source": "python_security_audit",
                "description": "Vuln.", "exploit_scenario": "Attack.",
                "recommendation": "Fix.", "confidence": "high",
            }],
            "summary": {"files_reviewed": 5, "high": 1, "medium": 0, "low": 0},
        }
        output = SecurityAuditOutput.model_validate(data)
        assert len(output.findings) == 1

    def test_security_audit_node_has_output_instructions(self):
        from agentpipe.nodes.python_security_audit import PythonSecurityAudit
        node = PythonSecurityAudit()
        assert "## Output" in node.system_prompt


class TestDocsReviewModels:
    def test_docs_review_output_validates(self):
        from agentpipe.nodes.docs_review import DocsReviewOutput
        data = {
            "findings": [{
                "file": "README.md", "line": 10, "severity": "MEDIUM",
                "category": "doc_drift", "source": "docs_review",
                "description": "Stale ref.", "recommendation": "Update.",
                "confidence": "high",
            }],
            "summary": {"files_reviewed": 5, "high": 0, "medium": 1, "low": 0},
        }
        output = DocsReviewOutput.model_validate(data)
        assert len(output.findings) == 1

    def test_docs_review_node_has_output_instructions(self):
        from agentpipe.nodes.docs_review import DocsReview
        node = DocsReview()
        assert "## Output" in node.system_prompt
