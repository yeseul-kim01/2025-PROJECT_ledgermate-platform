# examples/parse_policies.py
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