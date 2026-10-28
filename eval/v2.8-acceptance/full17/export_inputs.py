#!/usr/bin/env python3
"""Project only model-visible inputs using the existing 2.8 exporter."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
NEW_SKILL_ID=re.compile(r"408-(?:error-diagnosis|concept-followup|calculation-check)",re.IGNORECASE)

def _load_existing_exporter():
    for root in HERE.parents:
        source=root/"eval/v2.8-acceptance/export_inputs.py"
        if source.is_file() and source.resolve()!=Path(__file__).resolve():
            spec=importlib.util.spec_from_file_location("_full17_existing_input_exporter",source)
            if spec is None or spec.loader is None:
                raise ValueError("existing input exporter is unavailable")
            module=importlib.util.module_from_spec(spec)
            previous=sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode=True
                spec.loader.exec_module(module)
            finally:
                sys.dont_write_bytecode=previous
            return module
    raise ValueError("existing 2.8 input exporter was not found")

BASE=_load_existing_exporter()

def export_case(catalog: object,case_id: str,*,material_root: Path)->dict:
    # The baseline exporter remains responsible for all catalog, material path,
    # old Skill-ID and knowledge-ID checks. This adapter adds the three new IDs.
    if isinstance(catalog,dict) and isinstance(catalog.get("cases"),list):
        for case in catalog["cases"]:
            if isinstance(case,dict) and case.get("id")==case_id:
                turns=case.get("turns")
                if isinstance(turns,list) and any(isinstance(turn,str) and NEW_SKILL_ID.search(turn) for turn in turns):
                    raise ValueError("natural messages must not contain new Skill IDs")
    return BASE.export_case(catalog,case_id,material_root=material_root)

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("--catalog",type=Path,default=HERE/"natural-cases.json")
    args=parser.parse_args(argv)
    try:
        path=args.catalog.resolve(strict=True)
        catalog=json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=BASE._unique_object)
        output=export_case(catalog,args.case_id,material_root=path.parent/"materials")
    except (OSError,ValueError) as exc:
        print(f"input export failed: {exc}",file=sys.stderr)
        return 2
    json.dump(output,sys.stdout,ensure_ascii=False,indent=2)
    sys.stdout.write("\n")
    return 0

if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
