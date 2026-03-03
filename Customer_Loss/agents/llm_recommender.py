# =============================================
# agents/llm_recommender.py — LLM 기반 추천 보조 Agent
# =============================================

from __future__ import annotations
import os
import asyncio
from typing import List, Dict, Any

from openai import AsyncOpenAI
import json

class LLMRecommender:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def score_candidates(
        self,
        customer_id: str,
        purchase_history: List[str],
        candidates: List[str],
        collab_top: List[str],
        content_top: List[str]
    ) -> Dict[str, Any]:
        """LLM을 사용하여 후보 상품들에 대한 추천 점수와 이유를 생성"""
        
        # LLM에게 전달할 프롬프트 구성
        # 고객 정보, 구매 이력, 다른 추천 알고리즘의 결과를 모두 포함하여 종합적인 판단 유도
        prompt = f"""
        고객 ID: {customer_id}
        구매 이력: {purchase_history}
        협업 필터링 추천 후보: {collab_top}
        콘텐츠 기반 추천 후보: {content_top}
        최종 후보 상품: {candidates}

        위 정보를 기반으로 각 상품에 대해 0~1 사이의 추천 점수를 산출하고,
        JSON 형태로 반환하라.

        예시:
        {{
          "에스프레소머신": {{ "score": 0.9, "reason": "..." }},
          "핸드드립세트": {{ "score": 0.85, "reason": "..." }}
        }}
        """

        # OpenAI API 호출 - 비동기 클라이언트 사용
        response = await self.client.chat.completions.create(
            model="gpt-5.2",  # 사용할 LLM 모델
            messages=[
                {
                    "role": "system",
                    "content": "너는 이커머스 추천 엔진 보조 LLM이다. 각 상품에 대해 0과 1 사이의 점수(score)를 주고, 간단한 한국어 이유(reason)를 함께 JSON으로 반환해라. 반드시 '상품명: {\"score\": float, \"reason\": str}' 구조의 JSON만 출력해라."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3  # 낮은 temperature로 일관된 점수 생성
        )

        content = response.choices[0].message.content
        
        # message.content가 list일 수도 있으므로 처리 (일부 모델에서 리스트 형태로 반환)
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content)
        else:
            text = str(content)

        # 코드 블록이나 추가 텍스트 제거를 위해 JSON 부분만 파싱 시도
        # LLM이 마크다운 코드 블록 형식으로 반환할 수 있음
        text = text.strip()
        if "```" in text:
            # ```json ... ``` 형태 처리 - 코드 블록에서 JSON 부분만 추출
            parts = text.split("```")
            candidates = [p for p in parts if "{" in p and "}" in p]  # 중괄호가 있는 부분만 선택
            if candidates:
                text = candidates[0]

        # JSON 파싱 시도
        try:
            return json.loads(text)  # 성공하면 딕셔너리 반환
        except Exception:
            return {}  # 파싱 실패 시 빈 딕셔너리 반환
