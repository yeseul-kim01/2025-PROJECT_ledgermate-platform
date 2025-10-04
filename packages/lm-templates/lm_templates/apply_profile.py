def apply_profile(raw_html: str, profile: dict) -> dict:
    """
    입력: Raw HTML(Upstage), 매핑 Profile(YAML/JSON 파싱)
    출력: {"rows":[{"category":..., "actual_amount":..., ...}, ...], "confidence": 0.8}
    """
    # 1) 테이블 후보 탐색
    # 2) 헤더 매칭(동의어/유사도)
    # 3) 매칭 테이블 선택 + 열 인덱스 매핑
    # 4) formula/post_rules 적용
    # 5) confidence 산출
    return virtual_view