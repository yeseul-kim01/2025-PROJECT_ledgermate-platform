# examples/ingest_policy_pg.py

"""
LedgerMate — ingest_policy_pg.py

목적:
- 파서/청크 단계에서 만들어진 정책(규정) 청크 JSON(*.chunks.json)을
  Postgres에 '정책 메타 + 청크 본문' 형태로 일괄 적재한다.
- 같은 원본(같은 PDF 또는 같은 청크 JSON)을 중복 적재하지 않도록
  sha256 해시로 **멱등성(idempotency)**을 보장한다.

동작 흐름:
1) 청크 파일 로드
   - 입력: *.chunks.json (title, path, code, text, context_text, tables_json, meta 등)
2) 원본 식별값 계산
   - --source-pdf가 있으면 해당 PDF의 sha256을 사용
   - 없으면 청크 JSON 내용 자체 sha256(sha256_json)으로 대체
   - source_name(파일명)과 sha256을 정책 버전 기록에 함께 남김
3) DB 연결 (+ 필요 시 스키마 보장)
   - connect()로 Postgres 접속
   - 최초 1회만 ensure_schema(conn) 호출(주석 해제해서 사용)
4) RLS(행 수준 보안) 통과를 위한 테넌트 스코프 주입
   - SELECT set_config('app.org_id', %s, true) 로 세션 스코프 설정
   - 이후 모든 INSERT/UPSERT는 해당 org_id 범위 내에서만 허용
5) 정책 UPSERT + 청크 벌크 삽입
   - upsert_policy(): (org_id, version, source_name, sha256)로 정책 메타 UPSERT
   - bulk_insert_chunks(): 정책-조항 청크들을 벌크로 INSERT
   - 반환: policy_id(UUID), 삽입된 청크 개수

입출력/부작용:
- 입력: *.chunks.json, (선택) --source-pdf
- 출력: 콘솔에 policy_id와 삽입 건수 출력
- DB: policy(정책 메타) UPSERT, policy_chunk(또는 대응 테이블) 다건 INSERT
- 파일 생성 없음(읽기만 함)

환경 변수(.env):
- DATABASE_URL  : Postgres DSN (예: postgres://user:pass@127.0.0.1:5432/ledgermate)
- ORG_ID        : --org-id 기본값으로 사용(옵션)
※ load_dotenv() 로 자동 로드됨

의존 모듈(레포 내부):
- lm_store.pg.connect
- lm_store.pg.ensure_schema
- lm_store.pg.upsert_policy
- lm_store.pg.bulk_insert_chunks
- lm_store.pg.sha256_json

CLI 인자:
- chunks (positional) : *.chunks.json 경로
- --org-id            : 테넌트 ID (기본값: .env의 ORG_ID 또는 "demo.univ")
- --version (필수)    : 정책 버전(예: "2024.09", "v1.2.0")
- --source-pdf        : 원본 PDF 경로(선택, 있으면 PDF sha256을 정책 레코드에 저장)

사용 예:
  # 1) 최초 스키마 구성 시(한 번만):
  #   파이썬 REPL 또는 임시 코드에서 ensure_schema(conn) 호출
  #
  # 2) 정책 청크 적재:
  python examples/ingest_policy_pg.py out/policies/rules_2025.chunks.json \
    --org-id demo.univ \
    --version 2025.09 \
    --source-pdf data/policies/rules_2025.pdf

  # source-pdf 없이(청크 JSON만으로 식별):
  python examples/ingest_policy_pg.py out/policies/rules_2025.chunks.json \
    --org-id demo.univ --version 2025.09

트러블슈팅:
- DB 연결 실패 → DATABASE_URL 확인, psql로 접속 테스트
- RLS로 인한 권한 에러 → org_id 세션 설정(set_config) 확인
- 중복 삽입 방지 확인 → 같은 source_pdf(또는 같은 청크 JSON)로 두 번 실행 시 멱등 동작되는지 확인
- JSON 포맷 오류 → *.chunks.json이 to_chunks() 출력 포맷과 일치하는지 검증

설계 노트:
- 정책 메타의 (org_id, version, sha256, source_name)을 기록해
  정책 원본과 버전 추적, 중복 방지(멱등성)를 동시에 달성한다.
- bulk_insert_chunks는 트랜잭션 단위로 묶여 있어 대량 삽입 시에도 성능/일관성이 좋다.
- 향후 정책 폐지/대체 버전 관리가 필요하면 upsert_policy에 유효기간 컬럼(시행일/폐지일) 확장 추천.
"""


from __future__ import annotations
import os, sys, json, hashlib, pathlib, argparse
from dotenv import load_dotenv
from lm_store.pg import connect, ensure_schema, upsert_policy, bulk_insert_chunks, sha256_json

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def main(chunks_path: str, org_id: str, version: str, source_pdf: str | None):
    # 1) 청크 로드
    chunks = json.load(open(chunks_path, encoding="utf-8"))

    # 2) 원본 식별값
    if source_pdf:
        sha = file_sha256(source_pdf)
        source_name = pathlib.Path(source_pdf).name
    else:
        sha = sha256_json(chunks)  # pdf가 없으면 JSON 자체 해시로라도 중복 방지
        source_name = pathlib.Path(chunks_path).name

    # 3) DB 연결 + (최초 1회) 스키마 보장
    conn = connect()
    # ensure_schema(conn)  # 스키마 처음 만들 때만 주석 해제

    # 4) RLS 통과용 테넌트 지정
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)", (org_id,))
    conn.commit()

    # 5) policy upsert + 청크 벌크 저장
    policy_id = upsert_policy(
        conn,
        org_id=org_id,
        version=version,
        source_name=source_name,
        sha256=sha,
    )
    n = bulk_insert_chunks(conn, policy_id, org_id, chunks)

    print(f"✅ policy_id={policy_id} inserted_chunks={n} org_id={org_id} version={version}")

if __name__ == "__main__":
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", help="*.chunks.json 경로")
    ap.add_argument("--org-id", default=os.getenv("ORG_ID", "demo.univ"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--source-pdf", default=None)
    args = ap.parse_args()
    main(args.chunks, args.org_id, args.version, args.source_pdf)
