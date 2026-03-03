# llm_wrappers/anthropic_chat.py
"""
Anthropic Claude API 래퍼 모듈
Anthropic의 Claude 모델을 사용하여 텍스트 생성을 수행합니다.
지연 로딩 방식으로 API 키를 환경 변수에서 로드합니다.
"""
from anthropic import Anthropic
from config import get_anthropic_key, ANTHROPIC_DEFAULT_MODEL


class AnthropicChat:
    """
    Anthropic Claude wrapper (lazy env load)
    Claude API를 사용하여 채팅 완성을 수행하는 래퍼 클래스입니다.
    """

    def __init__(self, model: str = ANTHROPIC_DEFAULT_MODEL, temperature: float = 0.4):
        """
        AnthropicChat 초기화
        
        Args:
            model: 사용할 Claude 모델명 (기본값: 환경 변수 또는 "claude-sonnet-4-20250514")
            temperature: 생성 온도 (0.0~1.0, 높을수록 창의적)
        """
        # API 키는 지연 로딩 방식으로 실제 사용 시점에 로드
        self.client = Anthropic(api_key=get_anthropic_key())
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str, max_tokens: int = 1200):
        """
        시스템 프롬프트와 사용자 메시지를 받아 Claude로 텍스트를 생성합니다.
        
        Args:
            system: 시스템 프롬프트 (모델의 역할 설정)
            user: 사용자 메시지 (실제 요청 내용)
            max_tokens: 최대 생성 토큰 수
            
        Returns:
            튜플: (생성된 텍스트, 사용량 정보 딕셔너리)
        """
        # Claude API 호출
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,      
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        # 토큰 사용량 정보 추출
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        }

        # 응답 내용 추출 (content는 리스트 형태)
        parts = resp.content or []
        # 첫 번째 텍스트 블록의 내용을 추출
        text = parts[0].text.strip() if parts else ""

        return text, usage
