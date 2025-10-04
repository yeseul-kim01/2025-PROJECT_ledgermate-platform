# examples/parse_policies.py
"""
LedgerMate — parse_policies.py (Typer CLI)

목적:
- Upstage 문서 파서를 호출해 PDF를 JSON으로 변환하는 CLI 유틸리티.
- 단일 파일(one)과 배치(batch) 모드 제공.
- 결과는 디스크(JSON 파일)로만 저장하며, DB 적재는 하지 않음.

전제:
- .env 에 Upstage API 키가 있어야 함 (load_dotenv()로 자동 로드)
  - UPSTAGE_API_KEY=sk-...
  - (선택) UPSTAGE_API_BASE=https://api.upstage.ai/v1

명령:
1) 단일 파일 파싱
   python examples/parse_policies.py one <file.pdf> [--out out/파일.json] \
       [--formats html] [--b64 table] [--ocr force] [--coordinates] [--chart-recognition] \
       [--model document-parse] [--timeout 120] [-v/--quiet]

2) 배치 파싱 (글롭 패턴)
   python examples/parse_policies.py batch "data/policies-sample/*.pdf" \
       --out-dir out/policies \
       [다른 옵션 동일]

주요 옵션 설명:
- --out / --out-dir        : 출력 JSON 경로/디렉터리 (없으면 out/<파일명>.json 으로 자동)
- --formats                : 출력 포맷 리스트 (기본 ["html"])
- --b64                    : base64 인코딩할 대상 (기본 ["table"])
- --ocr                    : OCR 모드 (기본 "force")
- --coordinates            : 좌표 추출 여부 (기본 False)
- --chart-recognition      : 차트 인식 여부 (기본 True)
- --model                  : 문서 파싱 모델 이름 (기본 "document-parse")
- --timeout                : API 호출 타임아웃(초) (기본 120)
- -v / --verbose/--quiet   : 자세한 로그 출력 토글 (기본 True = verbose)

입출력:
- 입력: PDF(단일/여러 개)
- 출력: JSON 파일(동일 파일명.stem + ".json")
- DB 저장 없음

오류/트러블슈팅:
- 401 Unauthorized → API 키/결제 상태 확인(Upstage 콘솔)
- 파일 매칭 0건(batch) → 글롭 패턴 확인(쉘에서 따옴표 필수일 수 있음)
- 출력 경로 오류 → out 디렉터리 자동 생성하지만 권한/경로 확인 필요
- 네트워크/타임아웃 → --timeout 늘려 시도

비고:
- 생성된 JSON은 이후 청크 변환(to_chunks) 및 DB 적재 파이프라인의 입력으로 사용됨.
"""

from __future__ import annotations
import pathlib
from glob import glob
from typing import List
import typer
from dotenv import load_dotenv
from lm_docparse.pdfParser import call_document_parse

app = typer.Typer(help="Upstage Parser 연습용: 단일/배치 파싱 스크립트")

@app.callback()
def init():
    load_dotenv()

@app.command("one")
def parse_one(
    file: str = typer.Argument(..., help="파싱할 문서 경로"),
    out: str | None = typer.Option(None, "--out", help="기본: out/<파일명>.json"),
    ocr: str = typer.Option("force"),
    coordinates: bool = typer.Option(False),
    chart_recognition: bool = typer.Option(True),
    output_formats: List[str] = typer.Option(["html"], "--formats"),
    base64_encoding: List[str] = typer.Option(["table"], "--b64"),
    model: str = typer.Option("document-parse"),
    timeout: int = typer.Option(120),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v"),  # 기본 True로 변경
):
    p = pathlib.Path(file)
    if not p.exists():
        typer.secho(f"❌ 파일이 없습니다: {file}", fg="red"); raise typer.Exit(1)

    if out is None:
        out = str(pathlib.Path("out") / f"{p.stem}.json")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)

    typer.secho("▶ 시작: 문서 파싱", fg="cyan")
    typer.echo(f"  • file={p}")
    typer.echo(f"  • out={out}")
    typer.echo(f"  • ocr={ocr}, coord={coordinates}, chart={chart_recognition}, formats={output_formats}")

    call_document_parse(
        str(p), out,
        ocr=ocr, coordinates=coordinates, chart_recognition=chart_recognition,
        output_formats=output_formats, base64_encoding=base64_encoding,
        model=model, timeout=timeout, verbose=verbose,
    )

    typer.secho(f"✅ 완료: {out}", fg="green")

@app.command("batch")
def parse_batch(
    pattern: str = typer.Argument("data/policies-sample/*.pdf"),
    out_dir: str = typer.Option("out/policies", "--out-dir"),
    ocr: str = typer.Option("force"),
    coordinates: bool = typer.Option(False),
    chart_recognition: bool = typer.Option(True),
    output_formats: List[str] = typer.Option(["html"], "--formats"),
    base64_encoding: List[str] = typer.Option(["table"], "--b64"),
    model: str = typer.Option("document-parse"),
    timeout: int = typer.Option(120),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v"),
):
    files = sorted(glob(pattern))
    typer.secho(f"▶ 배치 시작: {len(files)}개, pattern={pattern}", fg="cyan")
    if not files:
        typer.secho("❌ 매치되는 파일이 없습니다.", fg="red"); raise typer.Exit(1)

    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for fp in files:
        name = pathlib.Path(fp).stem + ".json"
        out_path = str(pathlib.Path(out_dir) / name)
        try:
            typer.echo(f"  → {fp}")
            call_document_parse(
                fp, out_path,
                ocr=ocr, coordinates=coordinates, chart_recognition=chart_recognition,
                output_formats=output_formats, base64_encoding=base64_encoding,
                model=model, timeout=timeout, verbose=verbose,
            )
            typer.secho(f"    ✓ Saved {out_path}", fg="green")
            ok += 1
        except Exception as e:
            typer.secho(f"    ✖ 실패: {e}", fg="red")
            fail += 1
    typer.secho(f"종료: 성공 {ok} / 실패 {fail}", fg=("green" if fail == 0 else "yellow"))

if __name__ == "__main__":
    app()