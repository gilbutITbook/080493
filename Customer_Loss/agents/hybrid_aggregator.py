# =============================================
# agents/hybrid_aggregator.py — 하이브리드 추천 A2A 에이전트 + gRPC 서버
# =============================================
"""
HybridAggregatorAgent
- CollaborativeRecommendService(6104)와 ContentRecommendService(6105)를
  gRPC로 직접 호출하여 점수를 정규화/융합하는 A2A 에이전트
- LLM 점수를 결합해 최종 추천 점수를 계산
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

import os
import asyncio
import json
from pathlib import Path

import grpc
from google.protobuf import struct_pb2

import churn_pb2 as pb
import churn_pb2_grpc as pbg
from .grpc_utils import dict_to_struct, struct_to_dict, call_feature_agent_batch, normalize_scores

# LLM Recommender (없으면 LLM 비활성화)
try:
    from agents.llm_recommender import LLMRecommender  # type: ignore
except Exception:  # ImportError 등
    LLMRecommender = None  # type: ignore


def _get_openai_api_key() -> Optional[str]:
    """
    OpenAI API 키를 가져옵니다.
    1. 환경변수에서 먼저 확인 (MCP 클라이언트가 설정한 경우)
    2. 없으면 mcp.json 파일을 찾아서 읽기
    3. 그것도 없으면 None 반환
    """
    # 1. 환경변수에서 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # 2. mcp.json 파일 찾기 (프로젝트 루트부터 상위 디렉토리로 검색)
    current_dir = Path(__file__).parent.parent.absolute()
    search_dirs = [
        current_dir,  # 프로젝트 루트
        current_dir.parent,  # 상위 디렉토리
        Path.home() / ".config" / "cursor",  # Cursor 설정 디렉토리
        Path.home() / ".cursor",  # Cursor 설정 디렉토리 (대체)
    ]
    
    for search_dir in search_dirs:
        mcp_json_path = search_dir / "mcp.json"
        if mcp_json_path.exists():
            try:
                with open(mcp_json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # mcp.json 구조: {"mcp": {"servers": {"server_name": {"env": {"OPENAI_API_KEY": "..."}}}}}
                    servers = config.get("mcp", {}).get("servers", {})
                    for server_name, server_config in servers.items():
                        env = server_config.get("env", {})
                        if "OPENAI_API_KEY" in env:
                            api_key = env["OPENAI_API_KEY"]
                            if api_key:
                                print(f"[LLM] mcp.json에서 API 키를 찾았습니다: {mcp_json_path}")
                                return api_key
            except Exception as e:
                print(f"[LLM] mcp.json 읽기 실패 ({mcp_json_path}): {e}")
                continue
    
    return None


class HybridAggregatorAgent:
    """협업 + 콘텐츠 gRPC 호출로 하이브리드 점수 계산 (A2A + 선택적 LLM 결합)"""

    def __init__(
        self,
        collab_endpoint: str = "127.0.0.1:6104",
        content_endpoint: str = "127.0.0.1:6105",
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        self.collab_endpoint = collab_endpoint
        self.content_endpoint = content_endpoint
        self.feature_endpoint = feature_endpoint

        # LLM Recommender (OPENAI_API_KEY가 없거나 LLMRecommender 미설치면 None)
        self.llm_recommender = None
        self.llm_enabled = False
        if LLMRecommender is not None:
            api_key = _get_openai_api_key()
            if api_key:
                # 환경변수에 설정 (LLMRecommender가 os.getenv를 사용하므로)
                os.environ["OPENAI_API_KEY"] = api_key
                try:
                    self.llm_recommender = LLMRecommender()
                    self.llm_enabled = True
                    print("[LLM] LLMRecommender 초기화 성공 - LLM이 활성화되었습니다.")
                except Exception as e:
                    print(f"[LLM] LLMRecommender 초기화 실패: {e}")
                    self.llm_recommender = None
                    self.llm_enabled = False
            else:
                print("[LLM] OPENAI_API_KEY를 찾을 수 없습니다 (환경변수 또는 mcp.json). LLM이 비활성화됩니다.")
        else:
            print("[LLM] LLMRecommender 모듈을 import할 수 없습니다. LLM이 비활성화됩니다.")

    # ---------------------------------------------------------
    # gRPC로 협업/콘텐츠 추천 호출
    # ---------------------------------------------------------
    async def _call_collab(
        self, cid: str, all_feats: List[Dict[str, Any]], top_n: int
    ) -> List[Dict[str, Any]]:
        async with grpc.aio.insecure_channel(self.collab_endpoint) as channel:
            stub = pbg.CollaborativeRecommendServiceStub(channel)
            resp = await stub.RecommendCollaborative(
                pb.RecommendReq(
                    customer_id=cid,
                    all_features=[dict_to_struct(f) for f in all_feats],
                    top_n=top_n,
                )
            )
        return [struct_to_dict(x) for x in resp.items]

    async def _call_content(
        self, cid: str, all_feats: List[Dict[str, Any]], top_n: int
    ) -> List[Dict[str, Any]]:
        async with grpc.aio.insecure_channel(self.content_endpoint) as channel:
            stub = pbg.ContentRecommendServiceStub(channel)
            resp = await stub.RecommendContent(
                pb.RecommendReq(
                    customer_id=cid,
                    all_features=[dict_to_struct(f) for f in all_feats],
                    top_n=top_n,
                )
            )
        return [struct_to_dict(x) for x in resp.items]

    # ---------------------------------------------------------
    # LLM을 이용한 후보 재점수
    # ---------------------------------------------------------
    async def _llm_rescore(
        self,
        cid: str,
        all_feats: List[Dict[str, Any]],
        ranked_names: List[str],
        collab_pairs: List[Tuple[str, float]],
        content_pairs: List[Tuple[str, float]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        LLMRecommender를 사용하여 각 후보 상품에 대한 0~1 점수와 이유를 요청.
        반환: {상품명: {"score": float, "reason": str}, ...}
        """
        # LLM이 초기화되지 않았지만 API 키가 있으면 지연 초기화 시도
        if self.llm_recommender is None:
            if LLMRecommender is not None:
                api_key = _get_openai_api_key()
                if api_key:
                    # 환경변수에 설정 (LLMRecommender가 os.getenv를 사용하므로)
                    os.environ["OPENAI_API_KEY"] = api_key
                    try:
                        self.llm_recommender = LLMRecommender()
                        print("[LLM] LLMRecommender 지연 초기화 성공")
                    except Exception as e:
                        print(f"[LLM] LLMRecommender 지연 초기화 실패: {e}")
                        import traceback
                        traceback.print_exc()
                        return {}
                else:
                    print("[LLM] OPENAI_API_KEY를 찾을 수 없습니다 (환경변수 또는 mcp.json).")
                    return {}
            else:
                print("[LLM] LLMRecommender 모듈을 import할 수 없습니다.")
                return {}

        # 해당 고객의 원본 구매 이력 찾기
        purchase_history_raw = ""
        for f in all_feats:
            if f.get("고객ID") == cid:
                purchase_history_raw = f.get("원본_구매이력", "")
                break

        purchase_list = [x.strip() for x in purchase_history_raw.split(",") if x.strip()]
        collab_top = [name for name, _ in collab_pairs[:10]]
        content_top = [name for name, _ in content_pairs[:10]]

        try:
            print(f"[LLM] score_candidates 호출 시작 - 고객: {cid}, 후보 수: {len(ranked_names)}")
            result = await self.llm_recommender.score_candidates(
                customer_id=cid,
                purchase_history=purchase_list,
                candidates=ranked_names,
                collab_top=collab_top,
                content_top=content_top
            )
            if not result:
                print(f"[LLM] score_candidates가 빈 결과를 반환했습니다.")
            else:
                print(f"[LLM] score_candidates 성공 - {len(result)}개 상품 점수 획득")
            return result
        except Exception as e:
            # LLM 호출 실패 시 LLM 사용 안 함
            print(f"[LLM] score_candidates 호출 실패: {e}")
            import traceback
            traceback.print_exc()
            return {}

    # ---------------------------------------------------------
    # 하이브리드 추천 (협업 + 콘텐츠 + 선택적 LLM)
    # ---------------------------------------------------------
    async def recommend(
        self, cid: str, all_feats: List[Dict[str, Any]], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        # A2A: 다른 두 에이전트 서버에 직접 gRPC 호출 (병렬 실행)
        # top_n * 2개를 요청하여 충분한 후보 확보 (최소 5개)
        collab_items, content_items = await asyncio.gather(
            self._call_collab(cid, all_feats, max(top_n * 2, 5)),
            self._call_content(cid, all_feats, max(top_n * 2, 5)),
        )

        # (상품명, 점수) 튜플로 변환 - 점수 정규화를 위해 필요
        collab_pairs = [
            (it["상품명"], float(it.get("추천점수", 0.0))) for it in collab_items
        ]
        content_pairs = [
            (it["상품명"], float(it.get("추천점수", 0.0))) for it in content_items
        ]

        # 협업/콘텐츠 점수 정규화 후 합산
        # 각 알고리즘의 점수를 0~1 사이로 정규화하여 스케일 차이 해결
        nc = normalize_scores(collab_pairs)  # 협업 필터링 정규화 점수
        nt = normalize_scores(content_pairs)  # 콘텐츠 기반 정규화 점수

        # 두 알고리즘의 점수를 합산
        merged: Dict[str, float] = {}
        for k, v in nc.items():
            merged[k] = merged.get(k, 0.0) + v
        for k, v in nt.items():
            merged[k] = merged.get(k, 0.0) + v

        # 평균 계산 (두 알고리즘 점수의 평균)
        for k in list(merged.keys()):
            merged[k] /= 2.0

        # 메타 정보는 collab -> content 순으로 찾아서 사용
        # (collab이 우선, 없으면 content에서 가져옴)
        meta: Dict[str, Dict[str, Any]] = {}
        for it in collab_items + content_items:
            name = it["상품명"]
            meta.setdefault(
                name,
                {
                    "카테고리": it.get("카테고리", "기타"),
                    "가격": it.get("가격", 0),
                    "설명": it.get("설명", ""),
                },
            )

        # 1차 하이브리드 스코어 기반으로 상위 후보 선택
        # 점수 기준 내림차순 정렬 후 top_n개 선택
        ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:top_n]
        candidate_names = [name for name, _ in ranked]  # 상품명만 추출

        out: List[Dict[str, Any]] = []
        for name, score in ranked:
            info = meta.get(name, {"카테고리": "기타", "가격": 0, "설명": ""})
            out.append(
                {
                    "상품명": name,
                    "추천점수": float(round(score, 3)),  # 하이브리드 기본 점수
                    "카테고리": info["카테고리"],
                    "가격": info["가격"],
                    "설명": info["설명"],
                    "추천이유": "협업+콘텐츠 융합 하이브리드 점수",
                }
            )

        # -----------------------------------------------------
        # LLM 점수로 재정렬
        # -----------------------------------------------------
        # LLM이 활성화되어 있으면 항상 LLM 점수를 사용
        llm_debug_info = {
            "llm_enabled": self.llm_enabled,
            "llm_recommender_exists": self.llm_recommender is not None,
            "llm_recommender_class_exists": LLMRecommender is not None
        }
        
        if self.llm_enabled or LLMRecommender is not None:
            llm_results = await self._llm_rescore(
                cid, all_feats, candidate_names, collab_pairs, content_pairs
            )

            if not llm_results:
                # LLM 사용 불가/실패 시 경고만 출력하고 기본 추천 반환
                print("[LLM] LLM 결과가 없어 기본 추천만 반환합니다. (LLM 호출 실패 또는 환경변수 미설정)")
                # 디버깅 정보를 첫 번째 추천 항목에 추가
                if out:
                    out[0]["LLM_디버그"] = {**llm_debug_info, "llm_results_empty": True}
                return out
        else:
            # LLM이 완전히 비활성화된 경우
            print("[LLM] LLM이 비활성화되어 있어 기본 추천만 반환합니다.")
            # 디버깅 정보를 첫 번째 추천 항목에 추가
            if out:
                out[0]["LLM_디버그"] = {**llm_debug_info, "llm_disabled": True}
            return out
        
        print(f"[LLM] LLM 점수 적용 시작 - {len(llm_results)}개 상품")

        # LLM 점수를 기본 추천 결과에 결합
        final_out: List[Dict[str, Any]] = []
        for item in out:
            name = item["상품명"]
            raw_llm = llm_results.get(name, {})  # LLM 결과에서 해당 상품의 점수 가져오기
            llm_score = 0.0
            llm_reason = None

            # LLM 결과가 딕셔너리 형태인 경우 (score와 reason 포함)
            if isinstance(raw_llm, dict):
                try:
                    llm_score = float(raw_llm.get("score", 0.0))
                except Exception:
                    llm_score = 0.0
                llm_reason = raw_llm.get("reason")  # 추천 이유 추출
            # LLM 결과가 숫자만 있는 경우
            elif isinstance(raw_llm, (int, float)):
                llm_score = float(raw_llm)

            item["LLM점수"] = round(llm_score, 3)  # LLM 점수 추가
            # 기본 점수(협업+콘텐츠)와 LLM 점수의 평균으로 최종 점수 계산
            item["최종점수"] = round(
                (item["추천점수"] + item["LLM점수"]) / 2.0, 3
            )

            # LLM이 제공한 추천 이유가 있으면 사용 (없으면 기본 이유 유지)
            if llm_reason:
                item["추천이유"] = llm_reason

            final_out.append(item)

        # 최종 점수 기준 재정렬 (LLM 점수가 반영된 최종점수로 정렬)
        final_out.sort(key=lambda x: x.get("최종점수", x["추천점수"]), reverse=True)
        return final_out

    async def recommend_with_feature_call(
        self, customer_id: str, data_path: str, top_n: int = 10
    ) -> Dict[str, Any]:
        """고객 데이터 경로를 받아 Feature 에이전트를 호출하고 하이브리드 추천 수행 (A2A 직접 호출)"""
        # Feature 에이전트 직접 호출 (배치)
        all_features = await call_feature_agent_batch(data_path, self.feature_endpoint)
        
        # 하이브리드 추천 수행
        recommendations = await self.recommend(customer_id, all_features, top_n)
        
        # 구조화된 응답 반환 (이미지 형식)
        summary = f"고객 {customer_id}의 하이브리드 추천 {len(recommendations)}개를 생성했습니다."
        
        return {
            "ok": True,
            "summary": summary,
            "data": {
                "customer_id": customer_id,
                "recommendations": recommendations,
            },
            "parameters": {"customer_id": customer_id, "top_n": top_n},
            "next_steps": ["similar_customers - 유사 고객 탐색 요청"],
        }


class HybridRecommendService(pbg.HybridRecommendServiceServicer):
    """gRPC 서비스 구현 - 하이브리드 추천 서비스"""
    
    def __init__(
        self,
        collab_endpoint: str = "127.0.0.1:6104",
        content_endpoint: str = "127.0.0.1:6105",
        feature_endpoint: str = "127.0.0.1:6101",
    ) -> None:
        self.agent = HybridAggregatorAgent(
            collab_endpoint, content_endpoint, feature_endpoint
        )  # 하이브리드 추천 에이전트 인스턴스

    async def _recommend_from_data_async(self, customer_id: str, data_path: str, top_n: int) -> List[Dict[str, Any]]:
        """비동기 실행 래퍼 - data_path를 받아 Feature를 호출하고 하이브리드 추천"""
        result = await self.agent.recommend_with_feature_call(customer_id, data_path, top_n)
        return result.get("data", {}).get("recommendations", [])

    def RecommendHybridFromData(self, request: pb.RecommendFromDataReq, context) -> pb.JsonList:  # type: ignore[override]
        """gRPC 메서드 구현 - data_path를 받아 내부적으로 Feature를 호출하고 하이브리드 추천 (A2A)"""
        # 비동기 메서드를 동기적으로 실행하여 추천 결과 획득
        recs = asyncio.run(self._recommend_from_data_async(
            request.customer_id, 
            request.data_path, 
            request.top_n or 10
        ))
        # 결과를 gRPC JsonList로 변환하여 반환
        return pb.JsonList(items=[dict_to_struct(r) for r in recs])


async def serve(host: str = "127.0.0.1", port: int = 6106) -> None:
    """gRPC 서버 시작 및 실행 - 하이브리드 추천 서비스를 제공하는 독립 서버"""
    server = grpc.aio.server()  # 비동기 gRPC 서버 인스턴스 생성
    # HybridRecommendService를 서버에 등록 (gRPC 서비스 구현체 연결)
    pbg.add_HybridRecommendServiceServicer_to_server(HybridRecommendService(), server)
    # 서버가 수신할 포트 설정 
    server.add_insecure_port(f"{host}:{port}")
    await server.start()  # 서버 시작
    print(f"[grpc] HybridRecommendService running at {host}:{port}")
    # 서버가 종료될 때까지 대기 
    await server.wait_for_termination()


if __name__ == "__main__":
    """직접 실행 시 gRPC 서버 시작"""
    # 이 파일을 직접 실행하면 하이브리드 추천 서비스가 포트 6106에서 시작됨
    asyncio.run(serve())
