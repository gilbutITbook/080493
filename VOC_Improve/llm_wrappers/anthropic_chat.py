# ================================================================
# File: anthropic_chat.py
# Role: Anthropic Claude LLM Wrapper (async)
# ================================================================

# ============ 표준 라이브러리 및 외부 패키지 임포트 ============
# 운영체제 관련 기능 (환경변수 읽기)
import os
# Anthropic 비동기 클라이언트 (API 호출용)
from anthropic import AsyncAnthropic


# ============ Anthropic Claude LLM 래퍼 클래스 ============
class AnthropicChat:
    """
    Anthropic Claude Messages API를 사용하기 위한 비동기 래퍼 클래스입니다.
    
    Summarizer / Evaluator / Critic / Improver 등
    모든 Agent가 await self.llm(prompt) 형태로 호출함.
    따라서 __call__(str) -> str 형태를 반드시 구현해야 함.
    
    이 클래스는 함수처럼 호출 가능한 객체(callable)로 동작합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self, model: str = None):
        """
        AnthropicChat 인스턴스를 초기화합니다.
        
        Args:
            model: 사용할 Anthropic 모델명 (None이면 환경변수 또는 기본값 사용)
        """
        # ============ 모델명 설정 ============
        # 사용자가 지정한 모델명이 있으면 사용하고,
        # 없으면 환경변수 A2A_MODEL_POLICY을 확인하고,
        # 그것도 없으면 기본값 "claude-sonnet-4-20250514"를 사용합니다
        self.model = model or os.environ.get("A2A_MODEL_POLICY", "claude-sonnet-4-20250514")
        
        # ============ Anthropic 클라이언트 생성 ============
        # 환경변수 ANTHROPIC_API_KEY에서 API 키를 읽어와 클라이언트를 생성합니다
        # API 키가 없으면 클라이언트 생성은 되지만 실제 호출 시 에러가 발생합니다
        self.client = AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )

    # ============ 호출 가능한 객체 구현 ============
    async def __call__(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        클래스를 함수처럼 호출할 수 있도록 하는 메서드입니다.
        
        이 메서드를 통해 Anthropic Messages API를 호출하여
        프롬프트에 대한 응답을 받아옵니다.
        
        Args:
            prompt: LLM에게 전달할 프롬프트 텍스트
            max_tokens: 최대 생성 토큰 수 (기본값: 1024)
            
        Returns:
            str: LLM이 생성한 응답 텍스트
            
        호출 예시:
            llm = AnthropicChat()
            result = await llm("정책 개선안을 제안해줘")
        """
        # ============ API 호출 ============
        # 비동기로 Anthropic Messages API를 호출합니다
        response = await self.client.messages.create(
            model=self.model,  # 사용할 모델명
            max_tokens=max_tokens,  # 최대 토큰 수
            messages=[
                {"role": "user", "content": prompt}  # 사용자 메시지로 프롬프트 전달
            ]
        )
        
        # ============ 응답 추출 및 반환 ============
        # Anthropic Messages API 응답 구조:
        # response.content: List[ContentBlock], 각 block.text 사용
        # 응답 구조가 복잡하므로 안전하게 접근합니다
        try:
            if response.content and len(response.content) > 0:
                first_block = response.content[0]
                # text 속성을 가져오거나, 딕셔너리인 경우 get 메서드 사용
                text = getattr(first_block, "text", None)
                if text is None and isinstance(first_block, dict):
                    text = first_block.get("text", "")
                # text가 None이면 빈 문자열로 변환
                if text is None:
                    text = ""
                return text
            else:
                return ""
        except Exception as e:
            # 파싱 실패 시 빈 문자열 반환
            print(f"[AnthropicChat] Warning: Failed to parse response: {e}")
            return ""

