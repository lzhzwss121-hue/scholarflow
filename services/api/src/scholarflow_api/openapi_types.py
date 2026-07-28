from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GENERATED_HEADER = """// This file is generated from FastAPI OpenAPI.
// Do not edit by hand. Run `npm run generate:api-types`.

"""


def render_typescript_api_types(openapi: dict[str, Any]) -> str:
    schemas = openapi.get("components", {}).get("schemas", {})
    paths = openapi.get("paths", {})
    lines = [GENERATED_HEADER.rstrip(), "", "export interface components {", "  schemas: {"]
    for name in sorted(schemas):
        rendered = render_schema(schemas[name], indent=6)
        lines.append(f"    {json.dumps(name)}: {rendered};")
    lines.extend(["  };", "}", "", "export interface paths {"])
    for path in sorted(paths):
        methods = [
            method
            for method in ("get", "post", "put", "patch", "delete")
            if method in paths[path]
        ]
        lines.append(f"  {json.dumps(path)}: {{")
        for method in methods:
            operation = paths[path][method]
            operation_id = operation.get("operationId", "")
            lines.append(
                f"    {method}: {{ operationId: {json.dumps(operation_id)} }};"
            )
        lines.append("  };")
    lines.extend(
        [
            "}",
            "",
            "export type ApiSchema<Name extends keyof components[\"schemas\"]> =",
            "  components[\"schemas\"][Name];",
            "",
        ]
    )
    return "\n".join(lines)


def render_schema(schema: Any, *, indent: int = 0) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        return f'components["schemas"][{json.dumps(name)}]'
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        values = schema["enum"]
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in values) or "never"
    for union_key in ("anyOf", "oneOf"):
        if union_key in schema:
            rendered = unique(
                render_schema(item, indent=indent)
                for item in schema[union_key]
            )
            return " | ".join(rendered) or "unknown"
    if "allOf" in schema:
        rendered = unique(
            render_schema(item, indent=indent)
            for item in schema["allOf"]
        )
        return " & ".join(rendered) or "unknown"

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(
            render_schema({**schema, "type": item}, indent=indent)
            for item in schema_type
        )
    if schema_type == "null":
        return "null"
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        item_type = render_schema(schema.get("items", {}), indent=indent)
        return f"Array<{item_type}>"
    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        pad = " " * indent
        child_pad = " " * (indent + 2)
        members: list[str] = []
        for name, property_schema in properties.items():
            optional = "" if name in required else "?"
            rendered = render_schema(property_schema, indent=indent + 2)
            members.append(
                f"{child_pad}{json.dumps(name, ensure_ascii=False)}{optional}: {rendered};"
            )
        additional = schema.get("additionalProperties")
        if additional is True:
            members.append(f"{child_pad}[key: string]: unknown;")
        elif isinstance(additional, dict):
            members.append(
                f"{child_pad}[key: string]: {render_schema(additional, indent=indent + 2)};"
            )
        if not members:
            return "Record<string, never>"
        return "{\n" + "\n".join(members) + f"\n{pad}}}"
    return "unknown"


def unique(values) -> list[str]:
    return list(dict.fromkeys(values))


def write_typescript_api_types(target: Path) -> None:
    from scholarflow_api.main import app

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_typescript_api_types(app.openapi()),
        encoding="utf-8",
    )


def main() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    target = repository_root / "packages" / "schemas" / "src" / "api.generated.ts"
    write_typescript_api_types(target)
    print(target)


if __name__ == "__main__":
    main()
