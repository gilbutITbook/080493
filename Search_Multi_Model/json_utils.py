# json_utils.py
"""
JSON 파싱 유틸리티 함수 모듈
LLM 응답에서 JSON을 안전하게 추출하고 파싱합니다.
"""
import json


def safe_json_loads(text: str):
    """
    JSON 문자열을 안전하게 파싱합니다.
    파싱 실패 시 None을 반환하여 예외를 방지합니다.
    
    Args:
        text: 파싱할 JSON 문자열
        
    Returns:
        파싱된 JSON 객체 또는 None (실패 시)
    """
    try:
        return json.loads(text)
    except Exception:
        # 파싱 실패 시 None 반환 (예외 전파 방지)
        return None
