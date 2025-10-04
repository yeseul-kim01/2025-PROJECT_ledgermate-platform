packages/
└── lm-ocr/
    ├── pyproject.toml
    └── lm_ocr/
        ├── __init__.py
        ├── client.py        # Upstage API 호출 래퍼
        ├── schema.py        # 결과 스키마 (pydantic)
        ├── receipts.py      # OcrParser (파일→결과)
        ├── io.py            # 저장/로딩 유틸
        └── cli.py           # 콘솔 엔트리포인트 (lm-ocr)


출력물은 기본적으로 out/receipts/ 아래에

<basename>.ocr.json (정제 텍스트 + 메타)

<basename>.raw.json (Upstage 원본 응답)
