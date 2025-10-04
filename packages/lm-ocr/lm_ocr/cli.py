from __future__ import annotations
import argparse, os
from pathlib import Path
from dotenv import load_dotenv; load_dotenv()  # CLI에서만 .env 로드

from .client import UpstageClient
from .receipts import OcrParser
from .io import save_bundle

DEFAULT_OUT = "out/bills"

def main():
    parser = argparse.ArgumentParser(description="LedgerMate - Receipt OCR (Upstage)")
    parser.add_argument("file", help="이미지/PDF 경로")
    parser.add_argument("-o", "--outdir", default=DEFAULT_OUT, help=f"출력 디렉토리 (기본 {DEFAULT_OUT})")
    args = parser.parse_args()

    src = Path(args.file)
    if not src.exists():
        raise SystemExit(f"파일 없음: {src}")

    try:
        # 컨텍스트 매니저를 쓰면 세션 정리가 안전
        with UpstageClient() as client:
            parser_ = OcrParser(client)
            bundle = parser_.parse_file(str(src))
    except Exception as e:
        raise SystemExit(f"❌ OCR 요청 실패: {e}")

    basename = src.stem
    paths = save_bundle(bundle, args.outdir, basename)

    print("✅ OCR 추출 완료")
    print(f" - OCR 결과: {paths['ocr']}")
    print(f" - Raw 응답 : {paths['raw']}")

if __name__ == "__main__":
    main()
