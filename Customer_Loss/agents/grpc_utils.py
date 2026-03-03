# =============================================
# agents/grpc_utils.py — gRPC 공통 유틸리티
# =============================================
"""
gRPC 관련 공통 유틸리티 함수들

이 모듈은 모든 에이전트에서 공통으로 사용하는 gRPC 관련 헬퍼 함수들을 제공합니다.
- 데이터 타입 변환 (Python dict ↔ gRPC Struct)
- Feature 에이전트 배치 호출
- 점수 정규화

이 함수들은 A2A(Agent-to-Agent) 통신에서 반복적으로 사용되므로 공통 모듈로 분리했습니다.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple
import csv

import grpc
from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict

import churn_pb2 as pb
import churn_pb2_grpc as pbg


def dict_to_struct(d: Dict[str, Any]) -> struct_pb2.Struct:
    """
    Python 딕셔너리를 gRPC Struct로 변환
    
    gRPC 통신에서 Python 딕셔너리를 전송하기 위해 protobuf Struct 타입으로 변환합니다.
    모든 에이전트 간 통신에서 사용되는 공통 변환 함수입니다.
    
    Args:
        d: 변환할 Python 딕셔너리
    
    Returns:
        gRPC Struct 객체 (protobuf Struct 타입)
    
    Example:
        >>> data = {"고객ID": "CUST001", "구매건수": 5}
        >>> struct = dict_to_struct(data)
    """
    s = struct_pb2.Struct()
    s.update(d)  # 딕셔너리의 모든 키-값 쌍을 Struct에 복사
    return s


def struct_to_dict(s: struct_pb2.Struct) -> Dict[str, Any]:
    """
    gRPC Struct를 Python 딕셔너리로 변환
    
    gRPC 통신에서 받은 protobuf Struct를 Python 딕셔너리로 변환합니다.
    필드명을 보존하여 원본 데이터 구조를 유지합니다.
    
    Args:
        s: 변환할 gRPC Struct 객체 (protobuf Struct 타입)
    
    Returns:
        Python 딕셔너리 (필드명 보존)
    
    Example:
        >>> struct = ...  # gRPC 응답에서 받은 Struct
        >>> data = struct_to_dict(struct)
        >>> print(data["고객ID"])  # 필드명이 그대로 유지됨
    """
    # MessageToDict를 사용하여 필드명을 보존하면서 변환
    return MessageToDict(s, preserving_proto_field_name=True)


async def call_feature_agent_batch(
    data_path: str, feature_endpoint: str = "127.0.0.1:6101"
) -> List[Dict[str, Any]]:
    """
    Feature 에이전트를 배치 호출하여 모든 고객의 특징 추출 (공통 함수)
    
    CSV 파일의 모든 고객 데이터를 읽어서 Feature 에이전트에 배치로 전송하고,
    모든 고객의 특징 데이터를 한 번에 추출합니다.
    
    이 함수는 HybridAggregator, SimilarCustomers 등 여러 에이전트에서 공통으로 사용됩니다.
    A2A 구조에서 Feature 에이전트를 호출하는 표준 방법입니다.
    
    Args:
        data_path: 고객 데이터 CSV 파일 경로
        feature_endpoint: Feature 에이전트 gRPC 서버 주소 (기본값: "127.0.0.1:6101")
    
    Returns:
        모든 고객의 특징 데이터 리스트 (각 고객별 딕셔너리)
    
    Example:
        >>> features = await call_feature_agent_batch("customer.txt", "127.0.0.1:6101")
        >>> print(f"총 {len(features)}명의 고객 특징 추출 완료")
    """
    # 1. CSV 파일에서 모든 고객 데이터 로드
    all_customers = []
    with open(data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_customers.append(row)
    
    # 2. Feature 에이전트에 배치 호출 (포트 6101)
    async with grpc.aio.insecure_channel(feature_endpoint) as channel:
        stub = pbg.FeatureServiceStub(channel)
        # 모든 고객 행을 gRPC Struct로 변환
        rows = [dict_to_struct(row) for row in all_customers]
        req = pb.FeaturesBatchReq(rows=rows)
        resp = await stub.FeaturesBatch(req)
        # 응답을 Python 딕셔너리 리스트로 변환
        all_features = [struct_to_dict(x) for x in resp.items]
    
    return all_features


def normalize_scores(pairs: List[Tuple[str, float]]) -> Dict[str, float]:
    """
    점수 정규화 유틸 (공통 함수)
    
    추천 점수나 유사도 점수를 0~1 사이로 정규화합니다.
    최대값을 기준으로 모든 점수를 나누어 스케일을 통일합니다.
    
    이 함수는 HybridAggregator에서 협업 필터링과 콘텐츠 기반 점수를
    결합할 때 스케일 차이를 해결하기 위해 사용됩니다.
    
    Args:
        pairs: (이름, 점수) 튜플의 리스트
    
    Returns:
        정규화된 점수 딕셔너리 (이름: 0~1 사이의 점수)
    
    Example:
        >>> scores = [("상품A", 10.0), ("상품B", 5.0), ("상품C", 15.0)]
        >>> normalized = normalize_scores(scores)
        >>> # 결과: {"상품A": 0.667, "상품B": 0.333, "상품C": 1.0}
    """
    if not pairs:
        return {}
    
    # 최대 점수 찾기
    mx = max((s for _, s in pairs), default=1.0)
    
    # 최대값이 0 이하이면 모든 점수를 0으로 반환
    if mx <= 0:
        return {n: 0.0 for n, _ in pairs}
    
    # 최대값으로 나누어 0~1 사이로 정규화
    return {n: float(s) / mx for n, s in pairs}

