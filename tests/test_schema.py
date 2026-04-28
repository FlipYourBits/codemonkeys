from typing import Literal
from pydantic import BaseModel, Field
from agentpipe.schema import generate_output_instructions


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
