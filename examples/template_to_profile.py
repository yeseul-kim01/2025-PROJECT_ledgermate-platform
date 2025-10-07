#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
템플릿 PDF → Upstage 파싱 → 템플릿 JSON → budget_profile.json(초안) 생성
- 예산/결산 공용으로 쓰는 profile 초안
"""
import os, sys, json, subprocess, shlex
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    # packages 디렉토리나 pyproject.toml이 보이면 거기가 루트라고 가정
    for p in [cur, *cur.parents]:
        if (p / "packages").exists() or (p / "pyproject.toml").exists():
            return p
    return cur  # 못 찾으면 현재 위치

SCRIPT_PATH = Path(__file__).resolve()
ROOT = find_repo_root(SCRIPT_PATH.parent)
EXAMPLES = ROOT / "examples"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_PATH = OUT_DIR / "budget_profile.json"
TEMPLATE_JSON_PATH = OUT_DIR / "template.json"     # 구조 요약 JSON
RAW_JSON_PATH = OUT_DIR / "template.raw.json"      # Upstage 원 응답 JSON (html 포함)

STD_SECTIONS = {
    "expense_details": {
        # 원본 헤더명 → std key
        "세부 사업분야": "subgroup",
        "비목": "item",
        "세부내역": "description",
        "예산액(원)": "expected_amount",
        "결산액": "actual_amount",
        "집행액": "actual_amount",
        "코드": "budget_code",
        "비고": "note"
    },
    "expense_summary": {
        "비목": "item",
        "예산액(원)": "expected_amount",
        "전년 결산대비": "last_year_ratio",
        "비고": "note"
    },
    "revenue_summary": {
        "구분": "group",
        "내역": "item",
        "세부내역": "subitem",
        "금액(원)": "expected_amount",
        "비고": "note"
    }
}

def run(cmd: str):
    print(f"[run] {cmd}")
    proc = subprocess.run(shlex.split(cmd), cwd=str(ROOT))
    if proc.returncode != 0:
        print("❌ 명령 실행 실패")
        sys.exit(proc.returncode)

def main():
    if len(sys.argv) < 2:
        print("사용법: python examples/quick/template_to_profile.py <템플릿PDF> [budget|settlement]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).resolve()
    mode = (sys.argv[2] if len(sys.argv) > 2 else "budget").lower()
    if not pdf_path.exists():
        print(f"❌ 파일 없음: {pdf_path}")
        sys.exit(1)

    # 1) Upstage 파서 호출 (client_upstage.py)
    #    out: template.json(감지 스키마), template.raw.json(원 응답)
    cmd = f'python -m lm_templates.client_upstage "{pdf_path}" "{TEMPLATE_JSON_PATH}" --doc-type {mode}'
    run(cmd)

    # 2) profile(초안) 생성
    profile = {
        "template_id": f"local-{mode}-template-1",
        "name": pdf_path.name,
        "sections": {
            # NOTE: 간단화를 위해 한 섹션만 써도 충분히 테스트 가능
            "expense_details": {
                # std key → 원본 헤더명 (역매핑)
                "mapping": {
                    "subgroup": "세부 사업분야",
                    "item": "비목",
                    "description": "세부내역",
                    "expected_amount": "예산액(원)",
                    "actual_amount": "집행액",
                    "budget_code": "코드",
                    "note": "비고"
                },
                "post_rules": [
                    {"op":"strip_commas","cols":["expected_amount","actual_amount"]},
                    {"op":"coerce_int","cols":["expected_amount","actual_amount"]}
                ]
            }
        },
        "constraints": {
            "required": ["item"],
            "recommended": ["description"]
        },
        "source_template_json": str(TEMPLATE_JSON_PATH.relative_to(ROOT))
    }

    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ budget_profile.json 저장: {PROFILE_PATH}")

if __name__ == "__main__":
    main()
