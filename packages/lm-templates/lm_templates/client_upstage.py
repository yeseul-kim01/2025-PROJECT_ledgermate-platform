# packages/lm-templates/lm_templates/client_upstage.py
import os, requests

UPSTAGE_DP_URL = "https://api.upstage.ai/v1/document-digitization/document-parsing"

def parse_pdf_to_html(file_path: str) -> dict:
    api_key = os.environ["UPSTAGE_API_KEY"]
    with open(file_path, "rb") as f:
        r = requests.post(
            UPSTAGE_DP_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"output_format": "html"}  # html 또는 markdown
        )
    r.raise_for_status()
    return r.json()  # 보통 { "html": "...", ... } 형태