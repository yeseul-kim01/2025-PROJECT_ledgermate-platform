# -*- coding: utf-8 -*-
from ..apply_profile import apply_profile

def apply_profile_budget(raw_html: str, profile: dict) -> dict:
    """예산안 전용 어댑터(금액=expected_amount)"""
    return apply_profile(raw_html, profile, mode="budget")
