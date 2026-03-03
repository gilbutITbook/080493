# =============================================
# agents/feature_engineer.py — 고객 특징 엔지니어링 에이전트 + gRPC 서버
# =============================================
"""
FeatureEngineerAgent + FeatureService(gRPC)

- customer.txt에서 읽어온 원시 행(row)을 특징 벡터로 변환
- VectorBasedCategoryClassifier를 이용해 카테고리 분포/유사도 계산
- gRPC 서버(FeatureService)를 통해 다른 에이전트/오케스트레이터에서 호출

포트(기본): 6101
  python -m agents.feature_engineer
"""

from __future__ import annotations
from typing import Dict, Any, List

import asyncio
import grpc
from google.protobuf import struct_pb2

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from .grpc_utils import dict_to_struct, struct_to_dict

from utils import (
    KOREAN_HEADERS,
    parse_date,
    parse_purchase_history,
    today,
    days_between,
)
from vector_search import VectorBasedCategoryClassifier


# ---------- 내부 도메인 로직 ----------

class FeatureEngineerAgent:
    """고객 특징 엔지니어링 에이전트"""

    def __init__(self) -> None:
        self._vec = VectorBasedCategoryClassifier()

    def _categorize_top2(self, name: str) -> List[str]:
        """상품명 기준 상위 2개 카테고리 반환"""
        # 벡터 기반 분류기를 사용하여 상품명을 카테고리로 분류
        # threshold=0.3: 유사도가 0.3 이상인 카테고리만 선택
        results = self._vec.classify_product(name, threshold=0.3)
        # 상위 2개 카테고리만 추출 (카테고리명만, 점수 제외)
        cats = [c for c, _ in results[:2]]
        # 카테고리가 없으면 "기타" 반환
        return cats if cats else ["기타"]

    async def run_one(self, row: Dict[str, str]) -> Dict[str, Any]:
        """단일 고객 특징 추출"""

        cid = (row.get(KOREAN_HEADERS["id"]) or "").strip()
        signup = parse_date(row.get(KOREAN_HEADERS["signup"]))
        churn_date = parse_date(row.get(KOREAN_HEADERS["churn_date"]))
        churn_reason = (row.get(KOREAN_HEADERS["churn_reason"]) or "").strip() or None
        history_raw = (row.get(KOREAN_HEADERS["history"]) or "").strip()

        # 구매 이력 파싱: 날짜와 상품명 튜플 리스트로 변환
        purchases = parse_purchase_history(history_raw)
        # 마지막 구매일 추출 (구매 이력이 있으면 마지막 항목의 날짜)
        last_purchase = purchases[-1][0] if purchases else None
        # 최근 구매 후 경과 일수 계산 (오늘 - 마지막 구매일)
        recency = days_between(last_purchase, today())
        # 가입 후 경과 일수 계산 (오늘 - 가입일)
        tenure = days_between(signup, today())
        # 가입 후 탈퇴까지 일수 계산 (탈퇴일이 있으면)
        days_to_churn = days_between(signup, churn_date)
        # 총 구매 건수
        purchase_cnt = len(purchases)

        # 카테고리 분포 계산 (상위 2카테고리 기반)
        # 각 상품의 상위 2개 카테고리를 추출하여 카테고리별 구매 횟수 집계
        cats: Dict[str, int] = {}
        for _, name in purchases:
            for c in self._categorize_top2(name):
                cats[c] = cats.get(c, 0) + 1

        # 상세 카테고리/유사도 계산 (더 낮은 threshold로 더 많은 카테고리 포함)
        # threshold=0.2: 유사도가 0.2 이상인 모든 카테고리 포함
        detailed_categories: Dict[str, List[str]] = {}  # 카테고리별 상품명 리스트
        category_scores: Dict[str, List[float]] = {}  # 카테고리별 유사도 점수 리스트
        for _, name in purchases:
            results = self._vec.classify_product(name, threshold=0.2)
            for category, score in results:
                # 각 카테고리에 해당 상품명과 점수 추가
                detailed_categories.setdefault(category, []).append(name)
                category_scores.setdefault(category, []).append(score)

        # 카테고리별 평균 유사도 점수 계산
        avg_scores = {
            k: (sum(v) / len(v)) if v else 0.0 for k, v in category_scores.items()
        }

        return {
            "고객ID": cid,
            "회원가입일": signup.isoformat() if signup else None,
            "최근구매일": last_purchase.isoformat() if last_purchase else None,
            "구매건수": purchase_cnt,
            "구매카테고리분포": cats,
            "벡터기반_상세카테고리": detailed_categories,
            "카테고리별_유사도점수": avg_scores,
            "가입후일수": tenure,
            "최근구매후일수": recency,
            "탈퇴여부": bool(churn_date),
            "탈퇴일": churn_date.isoformat() if churn_date else None,
            "탈퇴사유": churn_reason,
            "원본_구매이력": history_raw,
            "가입후탈퇴까지일수": days_to_churn,
        }

    async def run_all(self, rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """여러 고객 특징 일괄 추출"""
        return [await self.run_one(r) for r in rows]


# ---------- gRPC Servicer ----------

class FeatureService(pbg.FeatureServiceServicer):
    """FeatureService gRPC 구현 (포트 6101)"""

    def __init__(self) -> None:
        self.agent = FeatureEngineerAgent()

    async def _run_one_async(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """단일 고객 특징 추출 비동기 실행"""
        return await self.agent.run_one(row)

    async def _run_all_async(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """여러 고객 특징 일괄 추출 비동기 실행"""
        return await self.agent.run_all(rows)

    # gRPC용 sync 래퍼 (grpcio-tools 기본 템플릿은 sync 메서드 시그니처)
    def FeaturesOne(self, request: pb.FeaturesOneReq, context) -> pb.Json:  # type: ignore[override]
        """gRPC 메서드 구현 - 단일 고객의 특징 추출 요청 처리"""
        row = struct_to_dict(request.row)  # gRPC Struct를 Python dict로 변환
        # 비동기 메서드를 동기적으로 실행하여 특징 데이터 획득
        result = asyncio.run(self._run_one_async(row))
        # 결과를 gRPC Json 메시지로 변환하여 반환
        return pb.Json(data=dict_to_struct(result))

    def FeaturesBatch(self, request: pb.FeaturesBatchReq, context) -> pb.JsonList:  # type: ignore[override]
        """gRPC 메서드 구현 - 여러 고객의 특징 일괄 추출 요청 처리"""
        rows = [struct_to_dict(s) for s in request.rows]  # 모든 행을 Python dict로 변환
        # 비동기 메서드를 동기적으로 실행하여 특징 데이터 리스트 획득
        result = asyncio.run(self._run_all_async(rows))
        # 결과를 gRPC JsonList로 변환하여 반환
        return pb.JsonList(items=[dict_to_struct(r) for r in result])


# ---------- 서버 부트스트랩 ----------

async def serve(host: str = "127.0.0.1", port: int = 6101) -> None:
    """gRPC 서버 시작 및 실행 - 특징 엔지니어링 서비스를 제공하는 독립 서버"""
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # FeatureService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_FeatureServiceServicer_to_server(FeatureService(), server)
    # 서버가 수신할 포트 설정 
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] FeatureService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 
    await server.wait_for_termination()


if __name__ == "__main__":
    """직접 실행 시 gRPC 서버 시작"""
    # 이 파일을 직접 실행하면 특징 엔지니어링 서비스가 포트 6101에서 시작됨
    # 사용법: python -m agents.feature_engineer
    asyncio.run(serve())
