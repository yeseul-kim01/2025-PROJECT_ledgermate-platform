import os, json, argparse
from pathlib import Path
from dotenv import load_dotenv

# 환경 로드는 오직 여기서만
load_dotenv()

from lm_settlement.pipeline import settle  # 라이브러리는 환경이 준비됐다고 가정

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True, help="영수증 JSON 경로")
    ap.add_argument("--profile", required=True, help="템플릿 프로필 JSON 경로")
    ap.add_argument("--org", default="demo.univ")
    ap.add_argument("--period", default="2024-2")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()

    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    result = settle(
        receipt=receipt,
        profile=profile,
        org_id=args.org,
        fiscal_period=args.period,
        api_key=args.api_key,
        base_url=args.base_url,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
