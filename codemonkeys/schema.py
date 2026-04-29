import json
import re
from typing import Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _field_example(annotation, field_info: FieldInfo):
    """Return an example value for a single field."""
    if field_info.examples:
        return field_info.examples[0]

    origin = get_origin(annotation)

    # Literal[...] — use first literal value
    if origin is Literal:
        return get_args(annotation)[0]

    # list[SomeModel] — recurse
    if origin is list:
        args = get_args(annotation)
        if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            return [_model_example(args[0])]
        return []

    # dict
    if origin is dict or annotation is dict:
        return {}

    # primitives
    if annotation is str:
        return "..."
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return True

    return None


def _model_example(cls: type[BaseModel]) -> dict:
    example = {}
    for name, field_info in cls.model_fields.items():
        annotation = field_info.annotation
        example[name] = _field_example(annotation, field_info)
    return example


def _literal_description_lines(
    field_name: str, annotation, field_info: FieldInfo
) -> str:
    """Render allowed values + meanings for a Literal field that has a description."""
    if get_origin(annotation) is not Literal:
        return ""
    description = field_info.description
    if not description:
        return ""

    values = get_args(annotation)
    # description format: "VAL1: meaning1. VAL2: meaning2."
    sentences = [s.strip() for s in description.split(". ") if s.strip()]
    # build mapping value -> meaning
    meaning = {}
    for sentence in sentences:
        for v in values:
            prefix = f"{v}:"
            if sentence.startswith(prefix):
                meaning[v] = sentence[len(prefix) :].strip()
                break

    label = field_name.capitalize()
    allowed = " | ".join(str(v) for v in values)
    lines = [f"\n{label} ({allowed}):"]
    for v in values:
        m = meaning.get(v, "")
        lines.append(f"- {v}: {m}" if m else f"- {v}")
    return "\n".join(lines)


def generate_output_instructions(cls: type[BaseModel]) -> str:
    example = _model_example(cls)
    json_block = json.dumps(example, indent=2)

    header = (
        "## Output\n\n"
        "Final reply must be a single fenced JSON block matching this schema and nothing after it:\n\n"
        f"```json\n{json_block}\n```"
    )

    # Append Literal descriptions
    extras = []
    for name, field_info in cls.model_fields.items():
        annotation = field_info.annotation
        desc = _literal_description_lines(name, annotation, field_info)
        if desc:
            extras.append(desc)

    return header + "".join(extras) + "\n"


def parse_output(cls: type[BaseModel], text: str) -> BaseModel:
    """Extract and validate a JSON object from model output text."""
    match = re.search(r"```json?\s*\n([\s\S]*?)\n\s*```", text)
    if match:
        json_str = match.group(1)
    elif text.strip().startswith("{"):
        json_str = text.strip()
    else:
        raise ValueError(f"No JSON found in response for {cls.__name__}")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for {cls.__name__}: {e}")

    try:
        return cls.model_validate(data)
    except Exception as e:
        raise ValueError(f"Validation failed for {cls.__name__}: {e}")
