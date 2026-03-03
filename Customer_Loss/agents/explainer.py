# =============================================
# agents/explainer.py — 예측 설명 에이전트 + gRPC 서버
# =============================================
"""
ExplainerAgent + ExplainerService(gRPC)

- Predictor와 Feature 에이전트를 직접 호출하여 예측 결과를 받아
  LLM 또는 템플릿 기반으로 설명 생성
- 여기서는 LLM 키가 없을 때도 동작하도록 간단한 규칙/템플릿 기반 설명 제공
"""

from __future__ import annotations
from typing import Dict, Any, Optional

import os
import asyncio
import grpc
from google.protobuf import struct_pb2

# gRPC 프로토콜 정의 파일들
import churn_pb2 as pb
import churn_pb2_grpc as pbg
# gRPC 통신을 위한 유틸리티 함수들 (dict ↔ Struct 변환)
from .grpc_utils import dict_to_struct, struct_to_dict

# OpenAI API 설정 (환경변수에서 로드)
from utils import OPENAI_API_KEY, OPENAI_MODEL

# OpenAI 클라이언트 import (선택적 - 미설치 환경 고려)
try:
    from openai import OpenAI
except Exception:  # openai 미설치 환경도 고려
    OpenAI = None  # type: ignore


# ---------- 도메인 로직 ----------

class ExplainerAgent:
    """이탈 예측 설명 에이전트 - Predictor와 Feature 에이전트를 직접 호출"""

    def __init__(
        self,
        predictor_endpoint: str = "127.0.0.1:6102",
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        """
        에이전트 초기화 - 다른 에이전트 엔드포인트 설정
        
        Args:
            predictor_endpoint: Predictor 에이전트 gRPC 서버 주소 (기본값: "127.0.0.1:6102")
            feature_endpoint: Feature 에이전트 gRPC 서버 주소 (기본값: "127.0.0.1:6101")
        """
        self.predictor_endpoint = predictor_endpoint  # 이탈 예측 에이전트 주소
        self.feature_endpoint = feature_endpoint  # 특징 추출 에이전트 주소
        self._client = None  # OpenAI 클라이언트 (초기에는 None)
        # OPENAI_API_KEY가 설정되어 있고 OpenAI 모듈이 있으면 클라이언트 초기화
        if OPENAI_API_KEY and OpenAI is not None:
            self._client = OpenAI(api_key=OPENAI_API_KEY)

    async def _call_predictor_agent(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predictor 에이전트를 직접 호출하여 예측 수행 (A2A 통신)
        
        Args:
            feature: 고객의 특징 데이터 딕셔너리
            
        Returns:
            예측 결과 딕셔너리 (churn_probability, churn_label 등 포함)
        """
        # 비동기 gRPC 채널 생성 (Predictor 에이전트와 통신)
        async with grpc.aio.insecure_channel(self.predictor_endpoint) as channel:
            stub = pbg.PredictorServiceStub(channel)  # gRPC 서비스 스텁 생성
            # 특징 데이터를 gRPC Struct로 변환하여 요청 생성
            req = pb.PredictOneReq(feature=dict_to_struct(feature))
            # PredictOne 메서드 호출하여 예측 수행
            resp = await stub.PredictOne(req)
            # 응답을 Python 딕셔너리로 변환하여 반환
            return struct_to_dict(resp.data)

    async def _call_feature_agent(self, customer_row: Dict[str, str]) -> Dict[str, Any]:
        """
        Feature 에이전트를 직접 호출하여 특징 추출 (A2A 통신)
        
        Args:
            customer_row: 원시 고객 행 데이터 딕셔너리 (CSV 파일의 한 행)
            
        Returns:
            특징 데이터 딕셔너리 (고객ID, 구매건수, 최근구매후일수 등 포함)
        """
        # 비동기 gRPC 채널 생성 (Feature 에이전트와 통신)
        async with grpc.aio.insecure_channel(self.feature_endpoint) as channel:
            stub = pbg.FeatureServiceStub(channel)  # gRPC 서비스 스텁 생성
            # 고객 행 데이터를 gRPC Struct로 변환하여 요청 생성
            req = pb.FeaturesOneReq(row=dict_to_struct(customer_row))
            # FeaturesOne 메서드 호출하여 특징 추출
            resp = await stub.FeaturesOne(req)
            # 응답을 Python 딕셔너리로 변환하여 반환
            return struct_to_dict(resp.data)

    async def run_one(self, pred: Dict[str, Any]) -> str:
        """
        예측 dict -> 설명 문자열 - 예측 결과를 자연어로 설명
        
        LLM이 사용 가능하면 LLM을 통해 상세한 설명을 생성하고,
        LLM이 없으면 레이블에 따라 규칙 기반 템플릿 설명을 제공합니다.
        
        Args:
            pred: 예측 결과 딕셔너리 (churn_label, churn_probability 등 포함)
            
        Returns:
            자연어 설명 문자열
        """
        label = pred.get("churn_label", "UNKNOWN")  # 이탈 위험도 레이블 (HIGH/MEDIUM/LOW)
        prob = pred.get("churn_probability", 0.0)  # 이탈 확률 (0.0 ~ 1.0)

        # 기본 설명 템플릿 (항상 포함) - 위험도와 확률 정보
        base = f"이 고객의 이탈 위험도는 {label} 등급이며, 추정 확률은 약 {prob:.0%}입니다. "

        # LLM 사용 가능 여부 확인
        if self._client is None:
            # LLM이 없으면 레이블에 따라 간단한 규칙 기반 설명 추가
            if label == "HIGH":
                return base + "최근 활동이 적고 구매 이력이 많지 않아 이탈 가능성이 높다고 판단했습니다."
            if label == "MEDIUM":
                return base + "일부 지표에서 이탈 징후가 보이지만 재참여 유도 여지가 남아 있습니다."
            # LOW 또는 기타 경우
            return base + "구매 활동과 가입 기간을 고려할 때 안정적인 고객으로 판단됩니다."

        # LLM 호출 - 더 상세하고 자연스러운 설명 생성
        # 예측 결과를 LLM에게 전달하여 설명 생성 요청
        prompt = (
            "다음 고객 이탈 예측 결과를 기반으로, 한국어로 3~4문장 정도의 간단한 설명을 작성해 주세요.\n\n"
            f"{pred}\n"
        )

        try:
            # OpenAI API는 동기 함수이므로 비동기 이벤트 루프에서 실행
            # run_in_executor를 사용하여 동기 함수를 비동기적으로 실행
            resp = await asyncio.get_event_loop().run_in_executor(
                None,  # 기본 스레드 풀 사용
                lambda: self._client.chat.completions.create(
                    model=OPENAI_MODEL,  # 사용할 LLM 모델 (기본값: gpt-5.2)
                    messages=[
                        {
                            "role": "system",
                            "content": "당신은 데이터 분석 결과를 쉽게 설명해주는 어시스턴트입니다.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,  # 낮은 temperature로 일관된 설명 생성
                ),
            )
            # LLM 응답이 있으면 사용, 없으면 기본 설명 반환
            return resp.choices[0].message.content or base
        except Exception:
            # LLM 호출 실패 시 기본 설명에 오류 메시지 추가
            # 예외 발생 시에도 기본 설명은 항상 제공하여 안정성 확보
            return base + "(LLM 호출 중 오류가 발생하여 기본 설명만 제공합니다.)"

    async def explain_with_direct_calls(
        self, customer_row: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        고객 행 데이터를 받아 Feature와 Predictor 에이전트를 직접 호출하고 설명 생성 (A2A 직접 호출)
        
        전체 파이프라인을 실행하는 메서드:
        1. Feature 에이전트 호출 → 특징 추출
        2. Predictor 에이전트 호출 → 예측 수행
        3. Explainer → 설명 생성
        
        Args:
            customer_row: 원시 고객 행 데이터 딕셔너리 (CSV 파일의 한 행)
            
        Returns:
            구조화된 응답 딕셔너리:
            - ok: 성공 여부
            - summary: 요약 메시지
            - data: 설명, 예측 결과, 특징 데이터 포함
            - parameters: 입력 파라미터
            - next_steps: 다음 단계 추천 액션
        """
        # 1단계: Feature 에이전트 직접 호출하여 특징 추출
        feature = await self._call_feature_agent(customer_row)
        # 2단계: Predictor 에이전트 직접 호출하여 예측 수행 (특징 데이터 사용)
        prediction = await self._call_predictor_agent(feature)
        # 3단계: 예측 결과를 바탕으로 설명 생성
        explanation = await self.run_one(prediction)
        
        # 구조화된 응답 반환 (이미지 형식)
        customer_id = customer_row.get("고객ID") or customer_row.get("customer_id", "")
        summary = (
            f"고객 {customer_id}의 이탈 예측 설명이 완료되었습니다. "
            f"예측 결과: {prediction.get('churn_label', 'UNKNOWN')} 위험도, "
            f"확률: {prediction.get('churn_probability', 0.0):.1%}"
        )
        
        # 예측 결과에 따른 다음 단계 액션 추천
        next_steps = []
        if prediction.get("churn_label") == "HIGH":
            # 고위험 고객의 경우 하이브리드 추천과 유사 고객 탐색 추천
            next_steps.append("recommend_hybrid - 하이브리드 추천 요청")
            next_steps.append("similar_customers - 유사 고객 탐색 요청")
        elif prediction.get("churn_label") == "MEDIUM":
            # 중위험 고객의 경우 콘텐츠 기반 추천 추천
            next_steps.append("recommend_content - 콘텐츠 기반 추천 요청")
        
        return {
            "ok": True,
            "summary": summary,
            "data": {
                "explanation": explanation,  # 생성된 설명 텍스트
                "prediction": prediction,  # 예측 결과 (확률, 레이블 등)
                "feature": feature,  # 추출된 특징 데이터
            },
            "parameters": {"customer_id": customer_id},
            "next_steps": next_steps,  # 다음 단계 추천 액션 리스트
        }


# ---------- gRPC Servicer ----------

class ExplainerService(pbg.ExplainerServiceServicer):
    """
    gRPC 서비스 구현 - 이탈 예측 설명 서비스
    
    독립적인 gRPC 서버(포트 6103)로 실행되어 다른 에이전트나 클라이언트에서
    예측 결과 설명을 요청할 수 있도록 합니다.
    """
    
    def __init__(
        self,
        predictor_endpoint: str = "127.0.0.1:6102",
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        """
        서비스 초기화
        
        Args:
            predictor_endpoint: Predictor 에이전트 gRPC 서버 주소
            feature_endpoint: Feature 에이전트 gRPC 서버 주소
        """
        # 예측 설명 에이전트 인스턴스 생성
        self.agent = ExplainerAgent(predictor_endpoint, feature_endpoint)

    async def _explain_from_row_async(self, customer_row: Dict[str, str]) -> str:
        """
        비동기 실행 래퍼 - customer_row를 받아 Feature와 Predictor를 호출하고 설명
        
        Args:
            customer_row: 원시 고객 행 데이터
            
        Returns:
            설명 문자열
        """
        # 전체 파이프라인 실행 (Feature → Predictor → Explainer)
        result = await self.agent.explain_with_direct_calls(customer_row)
        # 결과에서 설명 텍스트만 추출하여 반환
        return result.get("data", {}).get("explanation", "")

    def ExplainFromRow(self, request: pb.ExplainFromRowReq, context) -> pb.Text:  # type: ignore[override]
        """
        gRPC 메서드 구현 - customer_row를 받아 내부적으로 Feature와 Predictor를 호출하고 설명 (A2A)
        
        원시 고객 행 데이터만 받아서 내부적으로 Feature와 Predictor 에이전트를
        순차적으로 호출한 후 설명을 생성합니다. A2A 구조의 대표적인 사용 예시입니다.
        
        Args:
            request: ExplainFromRowReq 메시지 (customer_row 포함)
            context: gRPC 컨텍스트
            
        Returns:
            Text 메시지 (설명 문자열 포함)
        """
        customer_row = struct_to_dict(request.customer_row)  # 고객 행 데이터를 Python dict로 변환
        # 비동기 메서드를 동기적으로 실행하여 설명 텍스트 획득
        text = asyncio.run(self._explain_from_row_async(customer_row))
        # 결과를 gRPC Text 메시지로 변환하여 반환
        return pb.Text(value=text)


# ---------- 서버 부트 ----------

async def serve(host: str = "127.0.0.1", port: int = 6103) -> None:
    """
    gRPC 서버 시작 및 실행 - 예측 설명 서비스를 제공하는 독립 서버
    
    이 함수는 ExplainerService를 독립적인 gRPC 서버로 실행합니다.
    다른 에이전트나 클라이언트에서 이 서버에 연결하여 예측 결과 설명을 요청할 수 있습니다.
    
    Args:
        host: 서버가 바인딩할 호스트 주소 (기본값: "127.0.0.1")
        port: 서버가 수신할 포트 번호 (기본값: 6103)
    """
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # ExplainerService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_ExplainerServiceServicer_to_server(ExplainerService(), server)
    # 서버가 수신할 포트 설정 (insecure 채널 사용)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] ExplainerService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 (Ctrl+C 등으로 종료 신호를 받을 때까지 실행)
    await server.wait_for_termination()


if __name__ == "__main__":
    """
    직접 실행 시 gRPC 서버 시작
    
    이 파일을 직접 실행하면 예측 설명 서비스가 포트 6103에서 시작됩니다.
    예: python -m agents.explainer
    """
    # 비동기 서버 실행
    asyncio.run(serve())
