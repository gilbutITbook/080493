# config.py
"""
환경 변수 및 LLM 모델 설정 관리 모듈
각 LLM API 키와 모델명을 환경 변수에서 로드합니다.
"""
import os


def _require_env(name: str) -> str:
    """
    필수 환경 변수를 가져오는 헬퍼 함수
    
    Args:
        name: 환경 변수 이름
        
    Returns:
        환경 변수 값
        
    Raises:
        RuntimeError: 환경 변수가 설정되지 않은 경우
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


##########################################
#   LLM Model 설정 (지연 로딩 방식)
##########################################

# config.py

def get_openai_key():
    """
    OpenAI API 키를 환경 변수에서 가져옵니다.
    지연 로딩 방식으로 실제 사용 시점에 로드됩니다.
    
    Returns:
        OpenAI API 키 문자열
    """
    return _require_env("OPENAI_API_KEY")

def get_anthropic_key():
    """
    Anthropic API 키를 환경 변수에서 가져옵니다.
    지연 로딩 방식으로 실제 사용 시점에 로드됩니다.
    
    Returns:
        Anthropic API 키 문자열
    """
    return _require_env("ANTHROPIC_API_KEY")

# 각 LLM 모델의 기본 모델명 설정
# 환경 변수로 오버라이드 가능하며, 없으면 기본값 사용
OPENAI_DEFAULT_MODEL = os.getenv("A2A_OPENAI_MODEL", "gpt-5.2")
ANTHROPIC_DEFAULT_MODEL = os.getenv("A2A_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

