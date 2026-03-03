# orchestrator.py
# 오케스트레이터 모듈
# 여러 에이전트 서비스를 조율하여 제안서 생성 파이프라인을 실행합니다.
from __future__ import annotations
import asyncio
import grpc
import os
import json

import agents_pb2
import agents_pb2_grpc


class OrchestratorGrpc:
    """gRPC 기반 에이전트 오케스트레이터 클래스"""
    def __init__(
        self,
        competitor_addr: str = None,
    ):
        # 경쟁사 분석 서비스의 주소 설정
        # 인자로 전달된 주소가 있으면 사용, 없으면 환경변수 또는 기본값 사용
        self.addr_competitor = competitor_addr or os.getenv("COMPETITOR_ADDR", "localhost:6001")

    # --------------------------------------------------------------------
    # Internal call helpers
    # 경쟁사 분석 서비스를 호출하는 내부 헬퍼 메서드
    # --------------------------------------------------------------------
    async def _call_competitor(self, company: str, market: str, topk: int = 5, profiles_path: str = "", question: str = ""):
        """경쟁사 분석 서비스 호출 (초기 트리거)"""
        # 경쟁사 서비스에 연결
        async with grpc.aio.insecure_channel(self.addr_competitor) as ch:
            # 서비스 스텁 생성
            stub = agents_pb2_grpc.CompetitorServiceStub(ch)
            # 경쟁사 검색 요청 전송 (컨텍스트 포함하여 다음 에이전트로 전달)
            return await stub.Search(
                agents_pb2.CompetitorSearchRequest(
                    company=company,
                    market=market,
                    topk=topk,
                    profiles_path=profiles_path,
                    question=question,
                )
            )

    # --------------------------------------------------------------------
    # Public orchestration
    # 제안서 생성 파이프라인 실행
    # --------------------------------------------------------------------
    async def generate_proposal(
        self,
        question: str,
        profiles_path: str,
        company: str = "Azure AI Foundry",
        market: str = "FSI",
        out_dir: str = "outputs",
        out_filename: str | None = None,
        save: bool = True,
    ):
        """
        제안서 생성 파이프라인 실행 (에이전트 간 직접 통신 방식)
        
        Orchestrator는 초기 CompetitorAgent만 호출하며, 나머지는 에이전트 간 직접 통신으로 처리됩니다.
        흐름: CompetitorAgent → FormatterAgent → CustomerAgent → FeatureAgent → RevenueAgent → WriterAgent
        """
        # 환경변수 설정 (에이전트 간 통신을 위한 컨텍스트 전달)
        os.environ["COMPANY"] = company
        os.environ["MARKET"] = market
        os.environ["QUESTION"] = question
        os.environ["PROFILES_PATH"] = profiles_path
        if out_dir:
            os.environ["OUTPUT_DIR"] = out_dir
        if out_filename:
            os.environ["OUTPUT_FILENAME"] = out_filename
        
        # 1) CompetitorAgent만 호출 (나머지는 자동으로 체인되어 실행됨)
        comp = await self._call_competitor(company, market, 5, profiles_path, question)
        if not comp.ok:
            # 경쟁사 분석 실패 시 오류 반환
            return {"ok": False, "error": f"competitor: {comp.error}"}

        # 에이전트 간 직접 통신으로 모든 단계가 완료됨
        # 최종 결과는 WriterAgent가 파일로 저장하므로 여기서는 성공 여부만 반환
        return {
            "ok": True,
            "message": "제안서 생성 파이프라인이 시작되었습니다. 에이전트 간 직접 통신으로 처리됩니다.",
            "saved_path": None,  # WriterAgent가 저장 경로를 결정
        }


# 직접 실행 시 제안서 생성 파이프라인 실행
if __name__ == "__main__":
    import argparse
    # 명령줄 인자 파서 생성
    parser = argparse.ArgumentParser()
    # 필수 인자들 추가
    parser.add_argument("--company", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--question", required=True)
    # 선택적 인자들 추가
    parser.add_argument("--out-md")
    parser.add_argument("--out-dir", default="outputs")
    args = parser.parse_args()

    async def _run():
        """비동기 실행 함수"""
        # 오케스트레이터 인스턴스 생성
        orch = OrchestratorGrpc()
        # 제안서 생성 파이프라인 실행
        out = await orch.generate_proposal(
            question=args.question,
            profiles_path=args.profiles,
            company=args.company,
            market=args.market,
            out_dir=args.out_dir,
            out_filename=args.out_md,
            save=True,
        )
        # 결과를 JSON 형식으로 출력 (한글 인코딩 보존)
        print(json.dumps(out, ensure_ascii=False, indent=2))

    # 비동기 함수 실행
    asyncio.run(_run())
