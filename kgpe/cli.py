# -*- coding: utf-8 -*-
"""
KGPE command-line interface (for development/testing per the architecture
spec: "CLI for development and testing").

Usage:
  python -m kgpe.cli --request request.json
  python -m kgpe.cli --json '{"product_type":"flange","standard":"ASME_B16.5","size":"2","class_key":"150","pipe_schedule":"Sch40"}'
"""
import argparse
import json
import sys
from .generator import generate_geometry


def main(argv=None):
    p = argparse.ArgumentParser(prog="kgpe", description="KAFCO Geometry & Parametric Engine CLI")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--request", help="Path to a JSON request file")
    g.add_argument("--json", help="Inline JSON request string")
    p.add_argument("--indent", type=int, default=2)
    args = p.parse_args(argv)

    if args.request:
        with open(args.request, "r", encoding="utf-8") as f:
            request = json.load(f)
    else:
        request = json.loads(args.json)

    result = generate_geometry(request)
    print(json.dumps(result, indent=args.indent, default=str))
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
