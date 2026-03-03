# =============================================
# churn_mcp.py — 에이전트 간 직접 호출 방식 (A2A)
# =============================================
"""
MCP 서버 - 에이전트 간 직접 통신(A2A) 구조

이 파일은 MCP(Model Context Protocol) 서버로, Cursor·Claude Desktop 등 외부 도구와 연동합니다.
churn_mcp.py는 단순히 진입점 역할만 하며, 실제 조율은 에이전트들이 서로 직접 통신하여 수행합니다.

A2A(Agent-to-Agent) 구조:
- churn_mcp는 최상위 에이전트만 호출 (Predictor, Explainer, HybridAggregator, SimilarCustomers)
- 각 에이전트가 내부적으로 필요한 다른 에이전트를 gRPC로 직접 호출
- 예: Predictor → Feature, Explainer → Feature + Predictor, HybridAggregator → Feature + Collaborative + Content

노출되는 MCP 툴:
1. churn_predict_one: 이탈 확률 예측
2. churn_explain: 이탈 예측 설명
3. recommend_hybrid: 하이브리드 추천
4. similar_customers: 유사 고객 탐색
"""

from __future__ import annotations
import os
import csv
from typing import Dict, Any, Optional, List
from mcp.server.fastmcp import FastMCP
import grpc

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from agents.grpc_utils import dict_to_struct, struct_to_dict

# 프로젝트 루트 디렉토리 경로
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# MCP 서버 인스턴스 생성
mcp = FastMCP(name="Churn-A2A-MCP")


def abs_path(p: Optional[str]) -> str:
    """
    상대 경로를 절대 경로로 변환 - 프로젝트 루트 기준
    
    Args:
        p: 상대 경로 또는 None (None이면 기본값 "customer.txt" 사용)
    
    Returns:
        절대 경로 문자열
    """
    if p is None:
        p = "customer.txt"  # 기본값: 프로젝트 루트의 customer.txt
    if not os.path.isabs(p):
        # 상대 경로면 프로젝트 루트를 기준으로 절대 경로 생성
        p = os.path.join(PROJECT_ROOT, p)
    return p


def load_customer_row(customer_id: str, data_path: Optional[str] = None) -> Dict[str, str]:
    """
    고객 ID로 고객 데이터 행을 CSV 파일에서 로드
    
    Args:
        customer_id: 찾을 고객 ID
        data_path: CSV 파일 경로 (None이면 기본값 사용)
    
    Returns:
        고객 데이터 딕셔너리 (컬럼명: 값)
    
    Raises:
        ValueError: 고객을 찾을 수 없을 때
    """
    path = abs_path(data_path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # "고객ID" 또는 "customer_id" 컬럼에서 고객 ID 추출
            cid = row.get("고객ID") or row.get("customer_id") or ""
            if str(cid).strip() == str(customer_id).strip():
                return row
    raise ValueError(f"고객을 찾을 수 없습니다: {customer_id}")


@mcp.tool(name="churn_predict_one")
async def churn_predict_one(customer_id: str, data_path: Optional[str] = None):
    """
    단일 고객의 이탈 확률 예측 MCP 툴
    
    A2A 구조: churn_mcp → Predictor → (내부) Feature
    - Predictor 에이전트가 내부적으로 Feature 에이전트를 직접 호출하여 특징을 추출한 후 예측 수행
    
    Args:
        customer_id: 예측할 고객 ID
        data_path: 고객 데이터 CSV 파일 경로 (None이면 기본값 사용)
    
    Returns:
        이탈 예측 결과 (확률, 위험도 레이블 등)
    """
    # 1. 고객 데이터 로드
    customer_row = load_customer_row(customer_id, data_path)
    
    # 2. Predictor 에이전트 호출 (포트 6102)
    # Predictor가 내부적으로 Feature 에이전트를 직접 호출 (A2A)
    async with grpc.aio.insecure_channel("127.0.0.1:6102") as channel:
        stub = pbg.PredictorServiceStub(channel)
        # customer_row를 받아 내부적으로 Feature를 호출하는 메서드 사용
        req = pb.PredictFromRowReq(customer_row=dict_to_struct(customer_row))
        resp = await stub.PredictFromRow(req)
        result = struct_to_dict(resp.data)
    
    # 3. 결과 반환
    return {
        "ok": True,
        "summary": f"고객 {customer_id}의 이탈 예측이 완료되었습니다. 이탈 위험도: {result.get('churn_label', 'UNKNOWN')}, 이탈 확률: {result.get('churn_probability', 0.0):.1%}",
        "data": result,
        "parameters": {"customer_id": customer_id},
        "next_steps": ["churn_explain - 예측 설명 요청"] if result.get("churn_label") in ["HIGH", "MEDIUM"] else [],
    }


@mcp.tool(name="churn_explain")
async def churn_explain(customer_id: str, data_path: Optional[str] = None):
    """
    고객의 이탈 예측 설명 MCP 툴
    
    A2A 구조: churn_mcp → Explainer → (내부) Feature + Predictor
    - Explainer 에이전트가 내부적으로 Feature와 Predictor 에이전트를 직접 호출하여 예측 근거 설명 생성
    - LLM(gpt-5.2)을 사용하여 더 자연스러운 설명 생성 (OPENAI_API_KEY가 설정된 경우)
    
    Args:
        customer_id: 설명을 생성할 고객 ID
        data_path: 고객 데이터 CSV 파일 경로 (None이면 기본값 사용)
    
    Returns:
        이탈 예측에 대한 설명 텍스트
    """
    # 1. 고객 데이터 로드
    customer_row = load_customer_row(customer_id, data_path)
    
    # 2. Explainer 에이전트 호출 (포트 6103)
    # Explainer가 내부적으로 Feature와 Predictor를 직접 호출 (A2A)
    async with grpc.aio.insecure_channel("127.0.0.1:6103") as channel:
        stub = pbg.ExplainerServiceStub(channel)
        # customer_row를 받아 내부적으로 Feature와 Predictor를 호출하는 메서드 사용
        req = pb.ExplainFromRowReq(customer_row=dict_to_struct(customer_row))
        resp = await stub.ExplainFromRow(req)
        explanation = resp.value
    
    # 3. 결과 반환
    return {
        "ok": True,
        "summary": f"고객 {customer_id}의 이탈 예측 설명이 완료되었습니다.",
        "data": {
            "explanation": explanation,
        },
        "parameters": {"customer_id": customer_id},
        "next_steps": ["recommend_hybrid - 하이브리드 추천 요청", "similar_customers - 유사 고객 탐색 요청"],
    }


@mcp.tool(name="similar_customers")
async def similar_customers(customer_id: str, top_n: int = 10, data_path: Optional[str] = None):
    """
    유사 고객 탐색 MCP 툴
    
    A2A 구조: churn_mcp → SimilarCustomers → (내부) Feature
    - SimilarCustomers 에이전트가 내부적으로 Feature 에이전트를 직접 호출하여 모든 고객의 특징을 추출한 후
      코사인 유사도를 기반으로 유사 고객을 탐색
    
    Args:
        customer_id: 유사 고객을 찾을 기준 고객 ID
        top_n: 반환할 유사 고객 수 (기본값: 10)
        data_path: 고객 데이터 CSV 파일 경로 (None이면 기본값 사용)
    
    Returns:
        유사 고객 리스트 (고객ID, 유사도 점수 포함)
    """
    # 1. SimilarCustomers 에이전트 호출 (포트 6107)
    # SimilarCustomers가 내부적으로 Feature 에이전트를 직접 호출 (A2A)
    async with grpc.aio.insecure_channel("127.0.0.1:6107") as channel:
        stub = pbg.SimilarServiceStub(channel)
        # data_path를 받아 내부적으로 Feature를 호출하는 메서드 사용
        req = pb.SimilarFromDataReq(
            customer_id=customer_id,
            data_path=abs_path(data_path),
            top_n=top_n,
        )
        resp = await stub.SimilarCustomersFromData(req)
        similar_list = [struct_to_dict(item) for item in resp.items]
    
    # 2. 결과 반환
    return {
        "ok": True,
        "summary": f"고객 {customer_id}의 유사 고객 {len(similar_list)}명을 찾았습니다.",
        "data": {"similar_customers": similar_list},
        "parameters": {"customer_id": customer_id, "top_n": top_n},
        "next_steps": ["recommend_hybrid - 유사 고객 기반 추천 요청"],
    }


@mcp.tool(name="recommend_hybrid")
async def recommend_hybrid(customer_id: str, top_n: int = 10, data_path: Optional[str] = None):
    """
    하이브리드 추천 MCP 툴
    
    A2A 구조: churn_mcp → HybridAggregator → (내부) Feature + Collaborative + Content (+ LLM)
    - HybridAggregator 에이전트가 내부적으로 다음을 수행:
      ① Feature 에이전트를 배치 호출하여 모든 고객의 특징 추출
      ② Feature 결과를 사용하여 Collaborative와 Content 에이전트를 병렬 호출
      ③ 협업 필터링과 콘텐츠 기반 점수를 정규화하여 결합
      ④ LLM 점수를 선택적으로 결합 (OPENAI_API_KEY가 설정된 경우)
    
    Args:
        customer_id: 추천을 받을 고객 ID
        top_n: 반환할 추천 상품 수 (기본값: 10)
        data_path: 고객 데이터 CSV 파일 경로 (None이면 기본값 사용)
    
    Returns:
        하이브리드 추천 상품 리스트 (상품명, 추천점수, LLM점수, 최종점수 등 포함)
    """
    # 1. HybridAggregator 에이전트 호출 (포트 6106)
    # HybridAggregator가 내부적으로 Feature, Collaborative, Content를 직접 호출 (A2A)
    async with grpc.aio.insecure_channel("127.0.0.1:6106") as channel:
        stub = pbg.HybridRecommendServiceStub(channel)
        # data_path를 받아 내부적으로 Feature를 호출하고, 그 결과로 Collaborative와 Content를 호출하는 메서드 사용
        req = pb.RecommendFromDataReq(
            customer_id=customer_id,
            data_path=abs_path(data_path),
            top_n=top_n,
        )
        resp = await stub.RecommendHybridFromData(req)
        recommendations = [struct_to_dict(item) for item in resp.items]
    
    # 2. 결과 반환
    return {
        "ok": True,
        "summary": f"고객 {customer_id}의 하이브리드 추천 {len(recommendations)}개를 생성했습니다.",
        "data": {
            "customer_id": customer_id,
            "recommendations": recommendations,
        },
        "parameters": {"customer_id": customer_id, "top_n": top_n},
        "next_steps": ["similar_customers - 유사 고객 탐색 요청"],
    }


# =============================================
# MCP 서버 실행
# =============================================
if __name__ == "__main__":
    """직접 실행 시 MCP 서버 시작"""
    print("[Churn-A2A-MCP] MCP server running...")
    mcp.run(transport="stdio")
