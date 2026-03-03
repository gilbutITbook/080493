# =============================================
# agents/similar_customers.py — 유사 고객 탐색 + gRPC 서버
# =============================================

from __future__ import annotations
from typing import Dict, Any, List, Optional

import asyncio
import grpc
from google.protobuf import struct_pb2

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from .recommender_core import RecommenderCore
from .grpc_utils import dict_to_struct, struct_to_dict, call_feature_agent_batch


class SimilarCustomersAgent:
    """유사 고객 탐색 에이전트 - Feature 에이전트를 직접 호출하여 유사 고객을 찾음"""
    
    def __init__(self, feature_endpoint: str = "127.0.0.1:6101") -> None:
        """에이전트 초기화 - Feature 에이전트 엔드포인트 설정"""
        self.feature_endpoint = feature_endpoint
        self.core = RecommenderCore()  # 추천 시스템의 핵심 로직을 담당하는 공통 클래스
        self._built = False  # 고객-상품 행렬 구축 여부 플래그 (캐싱용)


    def _ensure_core(self, all_feats: List[Dict[str, Any]]) -> None:
        """고객-상품 행렬과 유사도 행렬을 구축 (한 번만 수행)"""
        if self._built:
            return  # 이미 구축되었으면 재구축하지 않음
        # 고객-상품 행렬 구축: 각 고객이 어떤 상품을 구매했는지 행렬로 표현
        self.core.build_customer_product_matrix(all_feats)
        # 상품 특징 정보 구축: 각 상품의 카테고리, 가격 등 메타데이터 생성
        self.core.build_product_features()
        # 고객 간 유사도 계산: 코사인 유사도를 사용하여 고객 간 유사도 행렬 생성
        self.core.calculate_customer_similarities()
        # 상품 간 유사도 계산: 상품 간 유사도 행렬 생성 (현재는 사용하지 않지만 일관성을 위해 계산)
        self.core.calculate_product_similarities()
        self._built = True  # 구축 완료 플래그 설정

    async def run(self, cid: str, all_feats: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """유사 고객 탐색 실행"""
        self._ensure_core(all_feats)  # 행렬 구축 확인
        # RecommenderCore의 similar_customers 메서드를 호출하여 유사 고객 리스트 획득
        pairs = self.core.similar_customers(cid, top_n)
        # 결과를 딕셔너리 리스트로 변환 (고객ID, 유사도)
        return [{"고객ID": c, "유사도": float(round(s, 3))} for c, s in pairs]

    async def find_similar_with_feature_call(
        self, customer_id: str, data_path: str, top_n: int = 10
    ) -> Dict[str, Any]:
        """고객 데이터 경로를 받아 Feature 에이전트를 호출하고 유사 고객 탐색 수행 (A2A 직접 호출)"""
        # Feature 에이전트 직접 호출 (배치)
        all_features = await call_feature_agent_batch(data_path, self.feature_endpoint)
        
        # 유사 고객 탐색 수행
        similar_list = await self.run(customer_id, all_features, top_n)
        
        # 구조화된 응답 반환 (이미지 형식)
        summary = f"고객 {customer_id}의 유사 고객 {len(similar_list)}명을 찾았습니다."
        
        return {
            "ok": True,
            "summary": summary,
            "data": {"similar_customers": similar_list},
            "parameters": {"customer_id": customer_id, "top_n": top_n},
            "next_steps": ["recommend_hybrid - 유사 고객 기반 추천 요청"],
        }


class SimilarService(pbg.SimilarServiceServicer):
    """gRPC 서비스 구현 - 유사 고객 탐색 서비스"""
    
    def __init__(self, feature_endpoint: str = "127.0.0.1:6101") -> None:
        self.agent = SimilarCustomersAgent(feature_endpoint)  # 유사 고객 탐색 에이전트 인스턴스

    async def _similar_from_data_async(self, customer_id: str, data_path: str, top_n: int) -> List[Dict[str, Any]]:
        """비동기 실행 래퍼 - data_path를 받아 Feature를 호출하고 유사 고객 탐색"""
        result = await self.agent.find_similar_with_feature_call(customer_id, data_path, top_n)
        return result.get("data", {}).get("similar_customers", [])

    def SimilarCustomersFromData(self, request: pb.SimilarFromDataReq, context) -> pb.JsonList:  # type: ignore[override]
        """gRPC 메서드 구현 - data_path를 받아 내부적으로 Feature를 호출하고 유사 고객 탐색 (A2A)"""
        # 비동기 메서드를 동기적으로 실행하여 유사 고객 리스트 획득
        res = asyncio.run(self._similar_from_data_async(
            request.customer_id,
            request.data_path,
            request.top_n or 10
        ))
        # 결과를 gRPC JsonList로 변환하여 반환
        return pb.JsonList(items=[dict_to_struct(r) for r in res])


async def serve(host: str = "127.0.0.1", port: int = 6107) -> None:
    """gRPC 서버 시작 및 실행 - 유사 고객 탐색 서비스를 제공하는 독립 서버"""
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # SimilarService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_SimilarServiceServicer_to_server(SimilarService(), server)
    # 서버가 수신할 포트 설정 
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] SimilarService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 
    await server.wait_for_termination()


if __name__ == "__main__":
    """직접 실행 시 gRPC 서버 시작"""
    # 이 파일을 직접 실행하면 유사 고객 탐색 서비스가 포트 6107에서 시작됨
    asyncio.run(serve())
