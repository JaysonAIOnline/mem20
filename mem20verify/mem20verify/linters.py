"""AST linters for the defect classes that actually shipped broken.

Each check exists because the corresponding bug reached production in this
repository. They are structural, not textual, so they do not fire on comments
or string literals.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    check: str
    message: str
    severity: str = "high"

    def as_dict(self) -> dict:
        return {
            "path": self.path, "line": self.line, "check": self.check,
            "message": self.message, "severity": self.severity,
        }


def _norm(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


# ---------------------------------------------------------------- branches
def _is_simple_assign(node: ast.AST) -> bool:
    return isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))


def _same_statements(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    return all(_norm(x) == _norm(y) for x, y in zip(a, b))


def _contains(haystack: list, needle: list) -> bool:
    """True if `needle` appears as a contiguous run inside `haystack`."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    return any(_same_statements(haystack[i:i + n], needle)
               for i in range(len(haystack) - n + 1))


def identical_branches(path: str, tree: ast.AST) -> list[Issue]:
    """Flag if/else whose arms are identical, or differ only by a side effect.

    The outage breaker shipped with an `if` that added one flag assignment and
    an `else` that did exactly the same logging. Textual equality alone misses
    it, so the second form is caught too: the arms share a common body and the
    `if` merely adds assignments.
    """
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or node.orelse is None:
            continue
        then_body, else_body = node.body, node.orelse

        if _same_statements(then_body, else_body):
            issues.append(Issue(
                path, node.lineno, "identical-branches",
                "if and else arms are identical; this condition has no effect",
            ))
            continue

        if len(else_body) == 1 and _contains(then_body, else_body):
            extra = [s for s in then_body if not _same_statements([s], else_body)]
            if extra and all(_is_simple_assign(s) for s in extra):
                names = []
                for stmt in extra:
                    targets = stmt.targets if isinstance(stmt, ast.Assign) else [
                        getattr(stmt, "target", None)]
                    for target in targets:
                        if target is not None:
                            names.append(_expr_name(target))
                issues.append(Issue(
                    path, node.lineno, "identical-branches",
                    "both arms run the same work; the if only assigns "
                    + (", ".join(n for n in names if n) or "a flag")
                    + " before it, so the branch cannot change the outcome",
                ))
    return issues


def _expr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


# ------------------------------------------------------------------- bounds
def unbounded_tests(path: str, tree: ast.AST) -> list[Issue]:
    """Flag `while True` and bare `fail_for=None` style hazards in tests.

    An unbounded test cannot terminate and takes the whole run with it.
    """
    issues: list[Issue] = []
    in_test = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            in_test = node.name.startswith("test")
        if not in_test:
            continue
        if (isinstance(node, ast.While) and not _is_none(node.test)
                and isinstance(node.test, ast.Constant)
                and node.test.value is True):
                issues.append(Issue(
                    path, node.lineno, "unbounded-loop",
                    "while True inside a test cannot terminate",
                ))
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "sleep" and node.args:
                first = node.args[0]
                if (isinstance(first, ast.Constant)
                        and isinstance(first.value, (int, float))
                        and first.value >= 30):
                        issues.append(Issue(
                            path, node.lineno, "long-sleep",
                            f"test sleeps {first.value}s; use a mock or short wait",
                            severity="medium",
                        ))
            for kw in node.keywords:
                if kw.arg in ("fail_for", "limit", "max") and _is_none(kw.value):
                    issues.append(Issue(
                        path, node.lineno, "unbounded-parameter",
                        f"{kw.arg}=None disables the bound and can hang the run",
                    ))
    return issues


# -------------------------------------------------------------------- regex
def misplaced_lookbehind(path: str, tree: ast.AST) -> list[Issue]:
    """Flag a lookbehind concatenated after a literal prefix.

    `"sk-" + r"(?<!...)" + body` anchors the lookbehind *after* the prefix. The
    preceding character is then the prefix's own last character, so if that
    character is in the boundary class every match is rejected and the pattern
    silently never fires. The lookbehind has to come first.
    """
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
            continue
        left, right = node.left, node.right
        if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
            continue
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            continue
        prefix, body = left.value, right.value
        if "(?<" not in body or not prefix:
            continue
        tail = prefix[-1]
        if tail in "-_." and f"[{tail}" not in prefix:
            issues.append(Issue(
                path, node.lineno, "misplaced-lookbehind",
                f"lookbehind follows {prefix!r}; it tests against {tail!r} and "
                "can never pass, so the pattern never matches",
            ))

    # chained concatenation: a lookbehind that is not the first operand but is
    # preceded by a non-empty literal. `A + B + C` parses as `((A+B)+C)`, so
    # only the outermost Add is examined; the nested ones would re-report.
    nested: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                and isinstance(node.left, ast.BinOp)):
            nested.add(id(node.left))

    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
            continue
        if id(node) in nested:
            continue
        operands: list[ast.AST] = []
        current: ast.AST = node
        while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Add):
            operands.append(current.right)
            current = current.left
        operands.append(current)
        operands.reverse()
        seen_literal = False
        for operand in operands:
            if not (isinstance(operand, ast.Constant)
                    and isinstance(operand.value, str)):
                continue
            value = operand.value
            if "(?<" in value and seen_literal:
                issues.append(Issue(
                    path, node.lineno, "misplaced-lookbehind",
                    "lookbehind is concatenated after a literal prefix; it must "
                    "be the first operand or the pattern never matches",
                ))
                break
            if value:
                seen_literal = True
    return _dedupe(issues)


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen: set[tuple] = set()
    unique: list[Issue] = []
    for issue in issues:
        key = (issue.check, issue.line, issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


# ------------------------------------------------------------------ surface
# Overrides whose whole purpose is to disable inherited behaviour. A `pass`
# body is the correct implementation for these, not a stub.
_BENIGN_NOOP_OVERRIDES = {
    "log_message",       # http.server.BaseHTTPRequestHandler logging
    "log_error",
    "write_gitignore",
    "get_help",
}


def noop_bodies(path: str, tree: ast.AST) -> list[Issue]:
    """Flag functions whose body is only `pass`/`...` outside ABC contracts.

    Abstract interface methods are exempt: they are legitimate contracts.
    """
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [n for n in node.body if not isinstance(n, ast.Expr)
                or not isinstance(n.value, ast.Constant)]
        if not body:
            continue
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            decorators = {
                getattr(d, "id", getattr(d, "attr", "")) for d in node.decorator_list
            }
            if decorators & {"abstractmethod", "overload"}:
                continue
            if node.name in _BENIGN_NOOP_OVERRIDES:
                continue
            issues.append(Issue(
                path, node.lineno, "noop-body",
                f"{node.name}() body is only pass",
                severity="medium",
            ))
    return issues


CHECKS = {
    "identical-branches": identical_branches,
    "misplaced-lookbehind": misplaced_lookbehind,
    "noop-body": noop_bodies,
}

ALL_CHECKS = (identical_branches, unbounded_tests, misplaced_lookbehind,
              noop_bodies)
