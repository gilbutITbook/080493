# llm_wrappers/openai_chat.py
"""
OpenAI Chat Completion API 래퍼 모듈
OpenAI의 GPT 모델을 사용하여 채팅 완성을 수행합니다.
지연 로딩 방식으로 API 키를 환경 변수에서 로드합니다.
"""
from openai import OpenAI
from config import get_openai_key, OPENAI_DEFAULT_MODEL


class OpenAIChat:
    """
    OpenAI Chat Completion wrapper (lazy env load)
    OpenAI API를 사용하여 채팅 완성을 수행하는 래퍼 클래스입니다.
    """

    def __init__(self, model: str = OPENAI_DEFAULT_MODEL, temperature: float = 0.7):
        """
        OpenAIChat 초기화
        
        Args:
            model: 사용할 GPT 모델명 (기본값: 환경 변수 또는 "gpt-5.2")
            temperature: 생성 온도 (0.0~2.0, 높을수록 창의적)
        """
        # API 키는 지연 로딩 방식으로 실제 사용 시점에 로드
        self.client = OpenAI(api_key=get_openai_key())
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str, max_tokens: int = 1200):
        """
        시스템 프롬프트와 사용자 메시지를 받아 GPT로 텍스트를 생성합니다.
        
        Args:
            system: 시스템 프롬프트 (모델의 역할 설정)
            user: 사용자 메시지 (실제 요청 내용)
            max_tokens: 최대 생성 토큰 수
            
        Returns:
            튜플: (생성된 텍스트, 사용량 정보 딕셔너리)
        """
        # OpenAI Chat Completions API 호출
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=max_tokens,
        )

        # 토큰 사용량 정보 추출
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }

        # 첫 번째 선택지의 메시지 내용 추출
        text = resp.choices[0].message.content.strip()
        return text, usage
