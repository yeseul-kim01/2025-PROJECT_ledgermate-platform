packages/
  lm-templates/                ← 신규
    lm_templates/
      __init__.py
      client_upstage.py        ← Upstage Document Parsing 호출 래퍼
      detector.py              ← HTML에서 템플릿(표/헤더) 감지
      normalize.py             ← 컬럼명/필드명 표준화(동의어 매핑)
      schema.py                ← TemplateSchema/Section/Table/Column dataclass
      persist.py               ← DB 적재 유틸(lm-store 재사용)
    pyproject.toml


# 모듈화

## 가상환경 활성화했다는 가정
pip uninstall -y lm-templates 2>/dev/null || true
pip install -e packages/lm-templates
pip install beautifulsoup4 requests  # 누락 시

## 검증

python -c "import lm_templates, pkgutil, os; print('file=', lm_templates.__file__); print('path=', list(lm_templates.__path__)); print('children=', os.listdir(list(lm_templates.__path__)[0]))"


## 실행 코드

export PYTHONPATH=$(pwd)
python examples/ingest_settlement_template.py data/templates-sample/결산안예시.pdf \
  out/templates/결산안예시.template.json
