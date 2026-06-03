import ast
import inspect
import re
from pathlib import Path

import yaml

ASSEMBLIES_DIR = Path(__file__).resolve().parents[1] / "assembling" / "assemblies"
REFERENCE_PATTERN = re.compile(r"\$\{([^}]+)\}")


class AssemblyDefaultsLoader(yaml.SafeLoader):
    pass


def _construct_ref(loader, node):
    return {"$ref": loader.construct_scalar(node)}


AssemblyDefaultsLoader.add_constructor("!Ref", _construct_ref)


def _coerce_scalar(value):
    if not isinstance(value, str):
        return value

    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _safe_eval(expression):
    tree = ast.parse(expression, mode="eval")
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
        ast.Load,
    )
    if not all(isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError(f"Unsupported expression in assembly defaults: {expression}")
    return eval(compile(tree, "<assembly-defaults>", "eval"), {"__builtins__": {}})


def _load_defaults():
    raw_defaults = yaml.load(
        (ASSEMBLIES_DIR / ("idex" + "_parameters.yaml")).read_text(),
        Loader=AssemblyDefaultsLoader,
    )["globals"]
    raw_context = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    ).get("context", {})
    raw_values = {**raw_context, **raw_defaults}
    resolved = {}

    def resolve(name):
        if name in resolved:
            return resolved[name]
        if name not in raw_values:
            raise KeyError(f"No assembly default named {name!r}")

        value = raw_values[name]
        resolved[name] = resolve_value(value)
        return resolved[name]

    def resolve_value(value):
        if isinstance(value, list):
            return [resolve_value(item) for item in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return resolve(value["$ref"])
            if "$expr" in value:
                expression = value["$expr"]["$sub"]
                expression = REFERENCE_PATTERN.sub(
                    lambda match: repr(resolve(match.group(1))),
                    expression,
                )
                return _safe_eval(expression)
            return {key: resolve_value(item) for key, item in value.items()}
        return _coerce_scalar(value)

    for name in raw_values:
        resolve(name)

    return resolved


DEFAULTS = _load_defaults()


def assembly_kwargs(factory, **overrides):
    signature = inspect.signature(factory)
    kwargs = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if name in overrides:
            kwargs[name] = overrides[name]
        elif name in DEFAULTS:
            kwargs[name] = DEFAULTS[name]
        elif parameter.default is inspect.Parameter.empty:
            raise KeyError(f"No default or override for {name!r}")
    return kwargs
