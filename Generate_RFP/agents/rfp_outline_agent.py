# agents/rfp_outline_agent.py
# RFP 목차 추출 에이전트 + gRPC 서버
#
# - 서비스 토픽: "outline.extract"
# - 기본 PDF: RFP.pdf (main.py / 호출 측에서 넘김)

import os, re, json
from typing import Any, Dict, List

import fitz  # PyMuPDF - PDF 텍스트 추출
from openai import AsyncOpenAI  # OpenAI API 클라이언트

from grpc_server import GrpcServer  # gRPC 서버 래퍼


class OutlineAgent:
    """
    RFP PDF 파일에서 제안서 목차를 추출/보정하는 에이전트

    - PDF 텍스트를 분석해 1~3차 목차를 생성
    - OpenAI 사용 가능 시 LLM 기반, 아니면 휴리스틱 기반
    """
    def __init__(self, client=None):
        # 에이전트 기본 정보 설정
        self.name = "outline_agent"
        self.description = "RFP PDF에서 1~3차 목차를 추출/보정"

    def _heuristic_outline(self, text: str) -> List[str]:
        """
        휴리스틱 기반 목차 추출 (LLM 사용 불가 시 대체 방법)
        - 정규표현식으로 번호가 있는 줄을 찾아 목차로 추출
        - 예: "1. 제목", "3.1 소제목" 등
        """
        # 각 줄을 공백 제거하여 정리
        lines = [ln.strip() for ln in text.splitlines()]
        # 번호 패턴이 있는 줄만 필터링 (예: "1. ", "3.1 ", "2) " 등)
        cand = [ln for ln in lines if re.match(r"^(\d+(\.\d+)*)[\)\.\s]+.+", ln)]

        # 중복 제거 및 정리
        out: List[str] = []
        for s in cand:
            # 연속된 공백을 하나로 통일
            s = re.sub(r"\s+", " ", s)
            # 중복되지 않으면 추가
            if s and s not in out:
                out.append(s)
            # 최대 25개까지만 수집
            if len(out) >= 25:
                break

        # 추출된 목차가 없으면 기본 목차 반환
        return out or ["1. 개요", "2. 요구사항", "3. 기술 제안", "4. 프로젝트 관리", "5. 가격/계약"]

    async def _handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        gRPC용 핸들러: topic = "outline.extract"
        payload: { "pdf_path": str, "hints": str? }
        """
        # 페이로드에서 파라미터 추출
        pdf_path = payload["pdf_path"]
        hints: str = (payload.get("hints") or "").strip()

        # 절대 경로 + 존재 여부 확인
        # 상대 경로인 경우 절대 경로로 변환
        if not os.path.isabs(pdf_path):
            pdf_path = os.path.abspath(pdf_path)
        # 파일 존재 여부 검증
        if not os.path.exists(pdf_path):
            return {"ok": False, "error": f"invalid pdf_path: {pdf_path}"}

        # PDF 텍스트 추출
        # PyMuPDF를 사용하여 모든 페이지의 텍스트 추출 (최대 4000자)
        with fitz.open(pdf_path) as doc:
            text = "\n".join(p.get_text() for p in doc)[:4000]

        # OpenAI API 키 확인
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        # API 키가 없으면 휴리스틱 방법 사용
        if not api_key:
            items = self._heuristic_outline(text)
            return {"ok": True, "outline": items}

        # OpenAI 클라이언트 초기화
        client = AsyncOpenAI(api_key=api_key)
        # LLM 프롬프트 구성
        # 목차 추출을 위한 지시사항과 힌트 포함
        prompt = f"""
아래 본문 일부를 보고 '1~3차 목차'를 JSON 배열로만 출력.
가능하면 번호/소번호 유지. 아래 힌트가 있으면 반영.

[힌트]
{hints or "없음"}

[본문 일부]
{text}
""".strip()

        # LLM을 사용한 목차 추출 시도
        try:
            # OpenAI API 호출
            # 낮은 temperature(0.2)로 일관된 결과 생성
            comp = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "너는 제안요청서 목차 전문가다. 오직 JSON 배열만 출력하라."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=120.0,
            )
            # LLM 응답에서 JSON 배열 추출
            content = (comp.choices[0].message.content or "").strip()
            # 정규표현식으로 JSON 배열 부분만 추출
            m = re.search(r"\[.*\]", content, re.DOTALL)
            items: List[str] = json.loads(m.group() if m else content)

            # 유효성 검증: 리스트 형태이고 비어있지 않아야 함
            if not isinstance(items, list) or not items:
                raise ValueError("LLM outline empty")
        except Exception:
            # LLM 호출 실패 시 휴리스틱 방법으로 대체
            items = self._heuristic_outline(text)

        # 목차 항목 정리 (공백 제거, 빈 항목 제외)
        items = [str(x).strip() for x in items if str(x).strip()]
        return {"ok": True, "outline": items}


# --------------------------
# gRPC 서버 부트스트랩
# --------------------------

async def _amain():
    """
    OutlineAgent 전용 gRPC 서버 실행
    - 주소: 환경변수 RFP_OUTLINE_ADDR (기본: 127.0.0.1:6051)
    - 토픽: "outline.extract"
    """
    # 환경변수에서 서버 주소 읽기 (기본값: 127.0.0.1:6051)
    addr = os.getenv("RFP_OUTLINE_ADDR", "127.0.0.1:6051")
    # 호스트와 포트 분리
    host, port_str = addr.rsplit(":", 1)

    # gRPC 서버 및 에이전트 인스턴스 생성
    server = GrpcServer(host=host, port=int(port_str))
    agent = OutlineAgent()

    # 헬스체크 핸들러 정의
    async def _health(_):
        return {"ok": True, "agent": agent.name}

    # 토픽별 핸들러 등록
    server.register("health.ping", _health)  # 헬스체크
    server.register("outline.extract", agent._handle)  # 목차 추출

    # 서버 시작 및 종료 대기
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_amain())
