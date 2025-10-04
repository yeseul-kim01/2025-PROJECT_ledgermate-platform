# packages/lm-rag/lm_rag/embeddings_upstage.py
from __future__ import annotations

import os
import re
from typing import List
from openai import OpenAI

# ===== Upstage Embedding 기본값 =====
DEFAULT_BASE_URL = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1")
DEFAULT_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")

# ===== 입력 텍스트 클린업 =====
# ASCII 제어문자 제거 (탭/개행 허용)
_CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def _clean_one(s: str, max_chars: int = 3500) -> str:
    s = str(s).strip()
    if not s:
        return ""
    s = _CTRL_RE.sub(" ", s)
    if len(s) > max_chars:
        s = s[:max_chars]
    return s


def _sanitize_texts(texts: List[str]) -> List[str]:
    cleaned = []
    for t in texts or []:
        if isinstance(t, (str, int, float)):
            s = _clean_one(t)
            if s:
                cleaned.append(s)
        # dict/list 등은 스킵
    return cleaned


def embed_texts(
    texts: List[str],
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    batch_size: int = 128,
) -> List[List[float]]:
    """
    Upstage(OpenAI SDK 호환) Embeddings 배치 호출.
    - 실패 배치 이분 탐색 분할(safe_call)로 문제 항목만 스킵.
    """
    client = OpenAI(
        api_key=api_key or os.getenv("UPSTAGE_API_KEY"),
        base_url=base_url or DEFAULT_BASE_URL,
    )
    use_model = model or DEFAULT_MODEL

    items = _sanitize_texts(texts)
    if not items:
        return []

    out: List[List[float]] = []

    def call_batch(batch: List[str]) -> List[List[float]]:
        resp = client.embeddings.create(model=use_model, input=batch)
        return [d.embedding for d in resp.data]

    def safe_call(batch: List[str]) -> List[List[float]]:
        try:
            return call_batch(batch)
        except Exception:
            if len(batch) == 1:
                print(f"[WARN] skip invalid text (len={len(batch[0])}): {batch[0][:80]!r}")
                return []
            mid = len(batch) // 2
            left = safe_call(batch[:mid])
            right = safe_call(batch[mid:])
            return left + right

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        out.extend(safe_call(batch))

    return out


# ===============================
# 4096 → 2000 축소 (JL Random Projection)
# ===============================
import numpy as np


def _make_projection_matrix(dim_in: int, dim_out: int, seed: int = 20251004) -> np.ndarray:
    """
    고정 시드 기반 랜덤 가우시안 투영행렬 (Johnson–Lindenstrauss)
    - 평균 0, 분산 1/dim_out 로 스케일 → L2 보존 성질 개선
    """
    rng = np.random.default_rng(seed)
    P = rng.standard_normal((dim_in, dim_out)).astype(np.float32)
    P /= np.sqrt(dim_out).astype(np.float32)
    return P


def reduce_embeddings(
    embs: List[List[float]],
    dim_out: int = 2000,
    assume_dim_in: int | None = None,
    seed: int = 20251004,
    l2_normalize: bool = True,
) -> List[List[float]]:
    """
    4096차원 임베딩을 2000차원으로 축소(또는 패딩).
    - dim_in > dim_out: 랜덤 투영
    - dim_in < dim_out: zero-pad
    - dim_in = dim_out: 그대로 통과
    """
    if not embs:
        return []

    dim_in = assume_dim_in or len(embs[0])

    arr = np.asarray(embs, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError("embs must be a 2D list/array")

    if arr.shape[1] != dim_in:
        # ragged 방어: 잘린/패딩으로 맞춤
        fixed = np.zeros((arr.shape[0], dim_in), dtype=np.float32)
        for i, v in enumerate(embs):
            n = min(len(v), dim_in)
            fixed[i, :n] = v[:n]
        arr = fixed

    if dim_in > dim_out:
        P = _make_projection_matrix(dim_in, dim_out, seed=seed)
        reduced = arr @ P
    elif dim_in < dim_out:
        reduced = np.zeros((arr.shape[0], dim_out), dtype=np.float32)
        reduced[:, :dim_in] = arr
    else:
        reduced = arr

    if l2_normalize:
        norms = np.linalg.norm(reduced, axis=1, keepdims=True) + 1e-12
        reduced = reduced / norms

    return reduced.tolist()
