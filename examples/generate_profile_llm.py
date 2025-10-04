# examples/generate_profile_llm.py (네가 준 코드 + 옵션 몇 개)
from pathlib import Path
import argparse, os, sys
from dotenv import load_dotenv

# lm_templates 패키지가 워크스페이스에 잘 잡히는지 확인
try:
    from lm_templates.llm_profile import save_inferred_profile
except Exception as e:
    print("[ERR] lm_templates.llm_profile import 실패:", e, file=sys.stderr)
    print("      PYTHONPATH에 packages/ 상위 디렉토리가 잡혀 있는지 확인하세요.", file=sys.stderr)
    raise

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="결산안 예시 JSON(파서 원본)")
    ap.add_argument("--out", dest="out_path", required=True, help="템플릿 프로필 JSON 저장 경로")
    ap.add_argument("--name", dest="name_hint", default=None, help="profile_id 생성 이름 힌트")
    ap.add_argument("--api-key", dest="api_key", default=None, help="Upstage API Key(미지정 시 .env/환경변수 사용)")
    ap.add_argument("--model", dest="model", default="solar-pro2", help="Upstage 모델명 (예: solar-pro2, solar-pro2-mini)")
    args = ap.parse_args()

    api_key = args.api_key or os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        print("[WARN] UPSTAGE_API_KEY 가 설정되지 않았습니다. .env 또는 --api-key 로 지정하세요.")

    # 저장 실행
    saved = save_inferred_profile(
        template_raw_json_path=Path(args.in_path),
        out_path=Path(args.out_path),
        api_key=api_key,
        profile_name_hint=args.name_hint,
    )
    print(f"[OK] Profile saved -> {saved}")

if __name__ == "__main__":
    main()
