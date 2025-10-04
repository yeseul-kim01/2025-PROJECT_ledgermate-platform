from __future__ import annotations
import os, time, requests
from typing import Dict, Any, BinaryIO, Optional

UPSTAGE_URL = "https://api.upstage.ai/v1/document-digitization"

class UpstageClient:
    def __init__(self, api_key: Optional[str] = None, timeout: int = 60):
        self.api_key = api_key or os.getenv("UPSTAGE_API_KEY")
        if not self.api_key:
            raise RuntimeError("UPSTAGE_API_KEY 환경변수가 필요합니다.")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def ocr(
        self,
        fileobj: BinaryIO,
        filename: str,
        model: str = "ocr",
        retries: int = 2,
        backoff: float = 1.2,
    ) -> Dict[str, Any]:
        files = {"document": (filename, fileobj)}
        data = {"model": model}
        last_err = None
        for i in range(retries + 1):
            try:
                resp = self._session.post(
                    UPSTAGE_URL, files=files, data=data, timeout=self.timeout
                )
                if resp.status_code == 429:
                    # rate limit: 지수 백오프
                    time.sleep((backoff ** i) * 1.0)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                time.sleep((backoff ** i) * 0.5)
        raise RuntimeError(f"Upstage OCR 실패: {last_err}")
    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()