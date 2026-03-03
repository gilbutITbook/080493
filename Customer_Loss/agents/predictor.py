# =============================================
# agents/predictor.py — 이탈 예측 에이전트 + gRPC 서버
# =============================================
"""
HeuristicPredictorAgent + PredictorService(gRPC)

- Feature 에이전트를 직접 호출하여 특징을 가져온 후
  churn_probability, churn_label 등을 계산
- 독립 gRPC 서버(포트 6102)로 실행되고,
  다른 에이전트에서 A2A로 직접 호출
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List

import asyncio
import grpc
from google.protobuf import struct_pb2

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from .grpc_utils import dict_to_struct, struct_to_dict


# ---------- 도메인 로직 ----------

class HeuristicPredictorAgent:
    """규칙 기반 이탈 예측 에이전트 - Feature 에이전트를 직접 호출"""

    def __init__(self, feature_endpoint: str = "127.0.0.1:6101"):
        """에이전트 초기화 - Feature 에이전트 엔드포인트 설정"""
        self.feature_endpoint = feature_endpoint

    async def _call_feature_agent(self, customer_row: Dict[str, str]) -> Dict[str, Any]:
        """Feature 에이전트를 직접 호출하여 특징 추출"""
        async with grpc.aio.insecure_channel(self.feature_endpoint) as channel:
            stub = pbg.FeatureServiceStub(channel)
            req = pb.FeaturesOneReq(row=dict_to_struct(customer_row))
            resp = await stub.FeaturesOne(req)
            return struct_to_dict(resp.data)

    async def run_one(self, feat: Dict[str, Any]) -> Dict[str, Any]:
        """특징 dict -> 예측 결과 dict - 규칙 기반 휴리스틱으로 이탈 확률 계산"""

        # 기본 값들 추출
        recency = feat.get("최근구매후일수") or 9999  # 최근 구매 후 경과 일수 (없으면 매우 큰 값)
        tenure = feat.get("가입후일수") or 0  # 가입 후 경과 일수
        purchase_cnt = feat.get("구매건수") or 0  # 총 구매 건수
        탈퇴여부 = bool(feat.get("탈퇴여부"))  # 이미 탈퇴한 고객 여부

        # 간단한 휴리스틱 점수 계산 (점수가 높을수록 이탈 가능성 높음)
        score = 0.0
        
        # 최근 구매 후 경과 일수가 길수록 이탈 가능성 증가
        # 1년(365일) 이상이면 점수 1.0, 최대 2.0까지 증가
        if recency is not None:
            score += min(recency / 365.0, 2.0)
        
        # 가입 후 경과 일수가 짧을수록 이탈 가능성 증가
        # 10년(3650일) 이상이면 점수 0.0 (안정적), 그보다 짧으면 점수 증가
        if tenure is not None:
            score += max(0.0, 1.0 - (tenure / 3650.0))  # 너무 오래된 고객은 안정적
        
        # 구매 건수가 적을수록 이탈 가능성 증가 (3건 미만이면 +0.8)
        if purchase_cnt is not None and purchase_cnt < 3:
            score += 0.8
        
        # 이미 탈퇴한 고객은 점수를 최대값으로 설정
        if 탈퇴여부:
            score = 1.0

        # 확률(0~1)로 정규화
        # 점수를 3.0으로 나누어 0~1 사이의 확률로 변환 (최대 점수는 약 3.8이지만 3.0으로 나눔)
        prob = max(0.0, min(score / 3.0, 1.0))

        # 확률에 따라 이탈 위험도 레이블 할당
        if prob >= 0.8:
            label = "HIGH"  # 높은 이탈 위험
        elif prob >= 0.4:
            label = "MEDIUM"  # 중간 이탈 위험
        else:
            label = "LOW"  # 낮은 이탈 위험

        return {
            "customer_id": feat.get("고객ID"),
            "churn_probability": float(prob),  # 이탈 확률 (0.0 ~ 1.0)
            "churn_label": label,  # 이탈 위험도 레이블 (HIGH/MEDIUM/LOW)
            "raw_score": float(score),  # 정규화 전 원시 점수 (디버깅용)
        }

    async def predict_with_feature_call(
        self, customer_row: Dict[str, str]
    ) -> Dict[str, Any]:
        """고객 행 데이터를 받아 Feature 에이전트를 호출하고 예측 수행 (A2A 직접 호출)"""
        # Feature 에이전트 직접 호출
        feat = await self._call_feature_agent(customer_row)
        # 예측 수행
        prediction = await self.run_one(feat)
        
        # 구조화된 응답 반환 (이미지 형식)
        customer_id = customer_row.get("고객ID") or customer_row.get("customer_id", "")
        summary = (
            f"고객 {customer_id}의 이탈 예측이 완료되었습니다. "
            f"이탈 위험도: {prediction['churn_label']}, "
            f"이탈 확률: {prediction['churn_probability']:.1%}"
        )
        
        next_steps = []
        if prediction["churn_label"] == "HIGH":
            next_steps.append("explain_high_risk - 고위험 고객에 대한 상세 설명 요청")
            next_steps.append("recommend_retention - 이탈 방지 추천 요청")
        elif prediction["churn_label"] == "MEDIUM":
            next_steps.append("explain_medium_risk - 중위험 고객에 대한 설명 요청")
            next_steps.append("recommend_engagement - 고객 참여도 향상 추천 요청")
        
        return {
            "ok": True,
            "summary": summary,
            "data": prediction,
            "parameters": {"customer_id": customer_id},
            "next_steps": next_steps,
        }


# ---------- gRPC Servicer ----------

class PredictorService(pbg.PredictorServiceServicer):
    """gRPC 서비스 구현 - 이탈 예측 서비스"""
    
    def __init__(self, feature_endpoint: str = "127.0.0.1:6101") -> None:
        self.agent = HeuristicPredictorAgent(feature_endpoint)  # 이탈 예측 에이전트 인스턴스

    async def _run_async(self, feat: Dict[str, Any]) -> Dict[str, Any]:
        """비동기 실행 래퍼"""
        return await self.agent.run_one(feat)

    def PredictOne(self, request: pb.PredictOneReq, context) -> pb.Json:  # type: ignore[override]
        """gRPC 메서드 구현 - 단일 고객의 이탈 예측 요청 처리"""
        feat = struct_to_dict(request.feature)  # gRPC Struct를 Python dict로 변환
        # 비동기 메서드를 동기적으로 실행하여 예측 결과 획득
        result = asyncio.run(self._run_async(feat))
        # 결과를 gRPC Json 메시지로 변환하여 반환
        return pb.Json(data=dict_to_struct(result))

    async def _predict_from_row_async(self, customer_row: Dict[str, str]) -> Dict[str, Any]:
        """비동기 실행 래퍼 - customer_row를 받아 Feature를 호출하고 예측"""
        return await self.agent.predict_with_feature_call(customer_row)

    def PredictFromRow(self, request: pb.PredictFromRowReq, context) -> pb.Json:  # type: ignore[override]
        """gRPC 메서드 구현 - customer_row를 받아 내부적으로 Feature를 호출하고 예측 (A2A)"""
        customer_row = struct_to_dict(request.customer_row)
        # 비동기 메서드를 동기적으로 실행하여 예측 결과 획득
        result = asyncio.run(self._predict_from_row_async(customer_row))
        # 결과를 gRPC Json 메시지로 변환하여 반환
        return pb.Json(data=dict_to_struct(result.get("data", result)))


# ---------- 서버 부트 ----------

async def serve(host: str = "127.0.0.1", port: int = 6102) -> None:
    """gRPC 서버 시작 및 실행 - 이탈 예측 서비스를 제공하는 독립 서버"""
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # PredictorService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_PredictorServiceServicer_to_server(PredictorService(), server)
    # 서버가 수신할 포트 설정 
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] PredictorService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 
    await server.wait_for_termination()


if __name__ == "__main__":
    """직접 실행 시 gRPC 서버 시작"""
    # 이 파일을 직접 실행하면 이탈 예측 서비스가 포트 6102에서 시작됨
    asyncio.run(serve())
