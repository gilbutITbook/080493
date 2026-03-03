# =============================================
# File: utils/json_utils.py
# =============================================
# LLM 응답을 안전하게 JSON으로 파싱하기 위한 유틸리티
#
# 주요 기능:
# - safe_json_loads: 문자열을 JSON으로 안전하게 변환
# - extract_json: LLM이 반환한 텍스트에서 JSON 블록만 추출
#
# 이 모듈은 LLM이 반환하는 다양한 형태의 JSON 응답을 안전하게
# 파싱하기 위한 유틸리티 함수들을 제공합니다.

# 필요한 라이브러리 import
import json
import re
from typing import Any, Dict, Optional


# ============ JSON 파싱 유틸리티 ============

def safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    """
    JSON 문자열을 안전하게 Dict로 변환하는 함수
    
    LLM이 반환하는 JSON 문자열의 일반적인 오류들을 자동으로 수정하여
    안전하게 파싱합니다. 실패 시 None을 반환합니다.

    Args:
        s (str): JSON 문자열 후보

    Returns:
        Optional[Dict[str, Any]]: 파싱된 딕셔너리 또는 None
    """
    # ============ 입력 검증 ============
    # 빈 문자열이면 None을 반환합니다
    if not s:
        return None
    
    # ============ 1단계: 기본 JSON 파싱 시도 ============
    # 표준 JSON 형식으로 파싱을 시도합니다
    try:
        return json.loads(s)
    except Exception:
        # ============ 2단계: 흔한 오류 수정 ============
        # LLM이 종종 작은따옴표를 사용하는 경우를 처리합니다
        # 작은따옴표를 큰따옴표로 치환하여 다시 파싱을 시도합니다
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            # ============ 3단계: 파싱 실패 처리 ============
            # 모든 시도가 실패하면 None을 반환합니다
            # 이 경우 호출하는 쪽에서 기본값을 사용하거나 다른 처리를 해야 합니다
            return None


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    텍스트에서 JSON 블록을 찾아 Dict로 반환하는 함수
    
    LLM이 설명과 JSON을 섞어서 반환하는 경우를 대비하여
    다양한 패턴으로 JSON 블록을 추출합니다.

    Args:
        text (str): LLM 응답 텍스트

    Returns:
        Optional[Dict[str, Any]]: 추출된 JSON 딕셔너리 또는 None
    """
    # ============ 입력 검증 ============
    # 빈 텍스트면 None을 반환합니다
    if not text:
        return None

    # ============ 1단계: 마크다운 코드 블록에서 JSON 추출 ============
    # LLM이 종종 마크다운 형식으로 JSON을 반환하는 경우를 처리합니다
    # ```json ... ``` 형식의 코드 블록을 찾습니다
    # re.S 플래그는 .이 줄바꿈도 매칭하도록 합니다
    m = re.search(r"```json(.*?)```", text, re.S)
    if m:
        # 코드 블록 안의 내용을 추출하여 파싱합니다
        return safe_json_loads(m.group(1).strip())

    # ============ 2단계: 중괄호 블록에서 JSON 추출 ============
    # 마크다운 코드 블록이 없으면 중괄호로 둘러싸인 첫 번째 블록을 찾습니다
    # { ... } 형식의 JSON 객체를 찾습니다
    m2 = re.search(r"\{.*\}", text, re.S)
    if m2:
        # 찾은 블록을 파싱합니다
        return safe_json_loads(m2.group(0).strip())

    # ============ 3단계: 전체 텍스트를 JSON으로 파싱 시도 ============
    # 위의 방법들이 실패하면 전체 텍스트를 JSON으로 파싱을 시도합니다
    # 앞뒤 공백을 제거한 후 파싱합니다
    return safe_json_loads(text.strip())
