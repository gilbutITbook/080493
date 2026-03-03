# =============================================
# agents/recommender_collaborative.py — 협업 필터링 추천 + gRPC 서버
# =============================================

from __future__ import annotations
from typing import Dict, Any, List, Optional

import asyncio
import grpc
from google.protobuf import struct_pb2

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from .recommender_core import RecommenderCore
from .grpc_utils import dict_to_struct, struct_to_dict, call_feature_agent_batch, normalize_scores


class CollaborativeRecommenderAgent:
    """협업 필터링 추천 에이전트"""
    
    def __init__(
        self,
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        """에이전트 초기화 - Feature 에이전트 엔드포인트 설정"""
        self.feature_endpoint = feature_endpoint
        self.core = RecommenderCore()  # 추천 시스템의 핵심 로직을 담당하는 공통 클래스
        self._built = False  # 고객-상품 행렬 구축 여부 플래그
        self._last_feats_hash = None  # 이전 특징 데이터의 해시값 (캐싱용)

    def _ensure_core(self, all_feats: List[Dict[str, Any]]) -> None:
        """고객-상품 행렬과 유사도 행렬을 구축 (데이터가 변경된 경우에만 재구축)"""
        if not all_feats:
            return  # 특징 데이터가 없으면 구축 불가
        
        # all_features의 해시를 계산해서 이전과 다르면 다시 구축
        # 고객ID와 구매이력만 사용하여 해시 계산 (효율적인 변경 감지)
        import hashlib
        feats_str = str(sorted([(f.get("고객ID", ""), f.get("원본_구매이력", "")) for f in all_feats]))
        feats_hash = hashlib.md5(feats_str.encode()).hexdigest()
        
        # 이미 구축되었고 해시값이 같으면 재구축하지 않음 (캐싱)
        if self._built and self._last_feats_hash == feats_hash:
            return
        
        # 고객-상품 행렬 구축: 각 고객이 어떤 상품을 구매했는지 행렬로 표현
        self.core.build_customer_product_matrix(all_feats)
        # 상품 특징 정보 구축: 각 상품의 카테고리, 가격 등 메타데이터 생성
        self.core.build_product_features()
        # 고객 간 유사도 계산: 코사인 유사도를 사용하여 고객 간 유사도 행렬 생성 (협업 필터링에 핵심)
        self.core.calculate_customer_similarities()
        # 상품 간 유사도 계산: 상품 간 유사도 행렬 생성 (현재는 사용하지 않지만 일관성을 위해 계산)
        self.core.calculate_product_similarities()
        self._built = True  # 구축 완료 플래그 설정
        self._last_feats_hash = feats_hash  # 현재 해시값 저장

    async def recommend(self, cid: str, all_feats: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """협업 필터링 기반 추천 실행 - 유사한 고객들이 구매한 상품 추천"""
        self._ensure_core(all_feats)  # 행렬 구축 확인
        # RecommenderCore의 recommend_collaborative 메서드를 호출하여 추천 상품 리스트 획득
        # 이 메서드는 유사한 고객들이 구매한 상품을 찾아 반환
        pairs = self.core.recommend_collaborative(cid, top_n)
        out: List[Dict[str, Any]] = []
        
        # 추천 결과를 딕셔너리 리스트로 변환 (상품명, 추천점수, 메타데이터 포함)
        for name, score in pairs:
            # 상품의 메타데이터 가져오기 (카테고리, 가격, 설명 등)
            info = self.core.product_features.get(name, {"category": "기타", "price": 0, "description": ""})
            out.append(
                {
                    "상품명": name,
                    "추천점수": float(round(score, 3)),  # 유사 고객들의 구매 패턴 기반 점수 (소수점 3자리)
                    "카테고리": info.get("category", "기타"),
                    "가격": info.get("price", 0),
                    "설명": info.get("description", ""),
                    "추천이유": "유사 고객 구매 패턴 기반 협업 추천",
                }
            )
        return out


class CollaborativeRecommendService(pbg.CollaborativeRecommendServiceServicer):
    """gRPC 서비스 구현 - 협업 필터링 추천 서비스"""
    
    def __init__(
        self,
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        self.agent = CollaborativeRecommenderAgent(feature_endpoint)  # 협업 필터링 추천 에이전트 인스턴스

    async def _run_async(self, cid: str, all_feats: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        """비동기 실행 래퍼"""
        return await self.agent.recommend(cid, all_feats, top_n)

    def RecommendCollaborative(self, request: pb.RecommendReq, context) -> pb.JsonList:  # type: ignore[override]
        """gRPC 메서드 구현 - 협업 필터링 추천 요청 처리"""
        cid = request.customer_id  # 요청에서 고객 ID 추출
        # gRPC Struct를 Python dict로 변환
        all_feats = [struct_to_dict(x) for x in request.all_features]
        # 비동기 메서드를 동기적으로 실행하여 추천 결과 획득
        recs = asyncio.run(self._run_async(cid, all_feats, request.top_n or 5))
        # 결과를 gRPC JsonList로 변환하여 반환
        return pb.JsonList(items=[dict_to_struct(r) for r in recs])


async def serve(host: str = "127.0.0.1", port: int = 6104) -> None:
    """gRPC 서버 시작 및 실행 - 협업 필터링 추천 서비스를 제공하는 독립 서버"""
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # CollaborativeRecommendService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_CollaborativeRecommendServiceServicer_to_server(
        CollaborativeRecommendService(), server
    )
    # 서버가 수신할 포트 설정 
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] CollaborativeRecommendService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 
    await server.wait_for_termination()


if __name__ == "__main__":
    """직접 실행 시 gRPC 서버 시작"""
    # 이 파일을 직접 실행하면 협업 필터링 추천 서비스가 포트 6104에서 시작됨
    asyncio.run(serve())
