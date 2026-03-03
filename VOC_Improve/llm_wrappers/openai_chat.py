# ================================================================
# File: openai_chat.py
# Role: OpenAI Chat LLM Wrapper (async)
# ================================================================

# ============ 표준 라이브러리 및 외부 패키지 임포트 ============
# 운영체제 관련 기능 (환경변수 읽기)
import os
# OpenAI 비동기 클라이언트 (API 호출용)
from openai import AsyncOpenAI


# ============ OpenAI Chat LLM 래퍼 클래스 ============
class OpenAIChat:
    """
    OpenAI Chat Completions API를 사용하기 위한 비동기 래퍼 클래스입니다.
    
    Summarizer / Evaluator / Critic / Improver 등
    모든 Agent가 await self.llm(prompt) 형태로 호출함.
    따라서 __call__(str) -> str 형태를 반드시 구현해야 함.
    
    이 클래스는 함수처럼 호출 가능한 객체(callable)로 동작합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self, model: str = None):
        """
        OpenAIChat 인스턴스를 초기화합니다.
        
        Args:
            model: 사용할 OpenAI 모델명 (None이면 환경변수 또는 기본값 사용)
        """
        # ============ 모델명 설정 ============
        # 사용자가 지정한 모델명이 있으면 사용하고,
        # 없으면 환경변수 OPENAI_MODEL을 확인하고,
        # 그것도 없으면 기본값 "gpt-5.2"를 사용합니다
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.2")
        
        # ============ OpenAI 클라이언트 생성 ============
        # 환경변수 OPENAI_API_KEY에서 API 키를 읽어와 클라이언트를 생성합니다
        # API 키가 없으면 클라이언트 생성은 되지만 실제 호출 시 에러가 발생합니다
        self.client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
        )

    # ============ 호출 가능한 객체 구현 ============
    async def __call__(self, prompt: str) -> str:
        """
        클래스를 함수처럼 호출할 수 있도록 하는 메서드입니다.
        
        이 메서드를 통해 OpenAI Chat Completions API를 호출하여
        프롬프트에 대한 응답을 받아옵니다.
        
        Args:
            prompt: LLM에게 전달할 프롬프트 텍스트
            
        Returns:
            str: LLM이 생성한 응답 텍스트
            
        호출 예시:
            llm = OpenAIChat()
            result = await llm("요약해줘")
        """
        # ============ API 호출 ============
        # 비동기로 OpenAI Chat Completions API를 호출합니다
        response = await self.client.chat.completions.create(
            model=self.model,  # 사용할 모델명
            messages=[
                {"role": "user", "content": prompt}  # 사용자 메시지로 프롬프트 전달
            ]
        )
        # ============ 응답 추출 및 반환 ============
        # 응답 객체에서 첫 번째 선택지의 메시지 내용을 추출하여 반환합니다
        return response.choices[0].message.content
