# -*- coding: utf-8 -*-
from ..apply_profile import apply_profile

def apply_profile_settlement(raw_html: str, profile: dict) -> dict:
    """결산안 전용 어댑터(금액=actual_amount)"""
    return apply_profile(raw_html, profile, mode="settlement")
