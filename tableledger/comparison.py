"""Conservative comparison retaining array order and identifier semantics."""
from .evaluation import exact
from .schema import json_loads


def equivalent(question, left, right):
    if not left or not right:
        return False
    try:
        target = json_loads(right) if question.question_type == 'structure' or question.answer_format == 'json_array' else right
        return exact(left, target, question.answer_format, question.question_type)
    except (ValueError, TypeError):
        return False
