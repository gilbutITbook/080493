# agents/compliance_matrix_agent.py
# RFP 자사 대응표 생성 에이전트 + gRPC 서버
#
# - 서비스 토픽: "compliance.build"
# - PDF: RFP.pdf
# - XLSX: RFP.rfp_compliance.xlsx (기본적으로 동일 이름으로 생성/덮어쓰기)
# - 에이전트 간 직접 통신: 필요 시 OutlineAgent를 gRPC로 직접 호출 (Orchestrator 없음)

import os, re, json
from typing import Any, Dict, List, Optional

import pandas as pd          # Excel 파일 생성
import fitz                  # PyMuPDF - PDF 텍스트 추출
from openai import AsyncOpenAI  # OpenAI API 클라이언트

from grpc_client import GrpcClient   # OutlineAgent 호출용
from grpc_server import GrpcServer   # gRPC 서버 래퍼


class ComplianceMatrixAgent:
    """
    RFP 요구사항 추출 및 자사 대응표(XLSX) 생성 에이전트

    - 에이전트 간 직접 통신: 필요 시 OutlineAgent를 gRPC로 직접 호출 (Orchestrator 없음)
    - 기본 출력 파일: <PDF파일명>.rfp_compliance.xlsx
      (예: RFP.pdf → RFP.rfp_compliance.xlsx)
    """
    def __init__(self, client: GrpcClient | None = None):
        # 에이전트 기본 정보 설정
        self.name = "compliance_matrix_agent"
        self.description = "RFP 요구사항 추출 및 자사 대응표(XLSX) 생성"

        # Outline gRPC 주소 (다른 에이전트)
        # 환경변수에서 주소를 가져오고, 없으면 기본값 사용
        outline_addr = os.getenv("RFP_OUTLINE_ADDR", "127.0.0.1:6051")
        # gRPC 클라이언트 초기화 (OutlineAgent와 통신용)
        self.client = client or GrpcClient(address=outline_addr, timeout_sec=300.0)

    async def _extract_text(self, pdf_path: str) -> str:
        """
        PDF 파일에서 텍스트 추출
        - PyMuPDF(fitz)를 사용하여 모든 페이지의 텍스트를 추출
        - 최대 6000자까지만 추출 (LLM 토큰 제한 고려)
        """
        with fitz.open(pdf_path) as doc:
            # 각 페이지의 텍스트를 추출하고 줄바꿈으로 연결
            # 슬라이싱으로 길이 제한
            return "\n".join(page.get_text() for page in doc)[:6000]

    async def _llm_requirements(
        self,
        text: str,
        outline: Optional[List[str]],
    ) -> List[Dict[str, str]]:
        """
        LLM을 사용하여 RFP 본문에서 요구사항 추출
        - OpenAI API를 통해 요구사항을 구조화된 JSON 배열로 변환
        - 목차 정보를 참고하여 분류 일관성 향상
        """
        # OpenAI API 키 확인 및 클라이언트 초기화
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        client = AsyncOpenAI(api_key=api_key)

        # LLM 프롬프트 구성
        # 요구사항 추출 및 구조화를 위한 지시사항 포함
        prompt = f"""
다음 RFP 본문(일부)에서 '요구사항'을 항목화하고 JSON 배열로만 출력.
각 객체: "요구사항", "중요도"(High/Medium/Low), "자사 대응"(초기는 ""), "비고"(근거/페이지).

가능하면 아래 목차를 참고해 분류 일관성을 높여라:
{json.dumps(outline or [], ensure_ascii=False)[:1600]}

본문:
{text}
""".strip()

        # OpenAI API 호출
        # 낮은 temperature(0.2)로 일관된 결과 생성
        comp = await client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": "너는 RFP 컴플라이언스 매트릭스 전문가다. 각 요구사항에 대한 자사 대응 방안을 반드시 포함하여 JSON 배열만 출력하라. 자사 대응 필드는 절대 비워두지 말라."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            timeout=180.0,
        )

        # LLM 응답에서 JSON 배열 추출
        content = (comp.choices[0].message.content or "").strip()
        # 정규표현식으로 JSON 배열 부분만 추출 (마크다운 코드 블록 등 제거)
        m = re.search(r"\[.*\]", content, re.DOTALL)
        items = json.loads(m.group() if m else content)

        # 유효성 검증: 리스트 형태이고 비어있지 않아야 함
        if not isinstance(items, list) or not items:
            raise ValueError("LLM requirements empty")

        return items

    def _save_xlsx_single(self, items: List[Dict[str, str]], out_path: str) -> None:
        """
        추출된 요구사항을 Excel 파일로 저장
        - pandas DataFrame을 사용하여 구조화된 데이터 생성
        - 필수 컬럼이 없으면 빈 문자열로 채움
        """
        # 딕셔너리 리스트를 DataFrame으로 변환
        df = pd.DataFrame(items)

        # 필수 컬럼이 없으면 빈 문자열로 초기화
        for col in ["요구사항", "중요도", "자사 대응", "비고"]:
            if col not in df.columns:
                df[col] = ""

        # 컬럼 순서 정렬 (요구사항, 중요도, 자사 대응, 비고)
        df = df[["요구사항", "중요도", "자사 대응", "비고"]]

        # 출력 디렉토리 생성 (없으면 생성)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        # 기존 파일이 있으면 삭제 (덮어쓰기)
        if os.path.exists(out_path):
            os.remove(out_path)

        # Excel 파일로 저장 (인덱스 제외)
        df.to_excel(out_path, index=False)

    def _coverage_gaps(
        self,
        outline: List[str],
        items: List[Dict[str, str]],
    ) -> List[str]:
        """
        목차와 추출된 요구사항을 비교하여 커버리지 갭 분석
        - 목차 항목이 요구사항에 포함되지 않으면 갭으로 표시
        - 최대 50개 목차, 10개 갭까지만 검사
        """
        # 모든 요구사항을 하나의 문자열로 결합
        body = "\n".join([i.get("요구사항", "") for i in items])
        gaps = []

        # 목차를 순회하며 요구사항에 포함 여부 확인
        for h in outline[:50]:
            # 목차 번호 제거 (예: "3.1 플랫폼" -> "플랫폼")
            key = re.sub(r"^\d+(\.\d+)*\s*", "", h).strip()
            # 키가 존재하고 요구사항 본문에 없으면 갭으로 판단
            if key and (key not in body):
                gaps.append(f"목차 '{h}' 관련 요구사항이 희박/부재함")
            # 최대 10개까지만 수집
            if len(gaps) >= 10:
                break
        return gaps

    async def _handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        gRPC용 핸들러: topic = "compliance.build"
        payload: { pdf_path, out_path?, outline?, hints? }
        """
        # 페이로드에서 파라미터 추출
        pdf_path: str = payload["pdf_path"]
        out_path: Optional[str] = payload.get("out_path")
        outline: Optional[List[str]] = payload.get("outline")

        # 절대 경로 + 존재 여부 확인
        # 상대 경로인 경우 절대 경로로 변환
        if not os.path.isabs(pdf_path):
            pdf_path = os.path.abspath(pdf_path)
        # 파일 존재 여부 검증
        if not os.path.exists(pdf_path):
            return {"ok": False, "error": f"invalid pdf_path: {pdf_path}"}

        # 에이전트 간 직접 통신: outline 없으면 gRPC로 OutlineAgent 직접 호출
        # Orchestrator 없이 에이전트 간 직접 통신으로 목차 정보 획득
        if not outline and self.client:
            oresp = await self.client.request(
                "outline.extract",
                {
                    "pdf_path": pdf_path,
                    "hints": payload.get("hints", ""),
                },
            )
            # OutlineAgent 호출 실패 시 에러 반환
            if not oresp.get("ok"):
                return {"ok": False, "error": f"outline request failed: {oresp.get('error')}"}
            # 추출된 목차 저장
            outline = oresp.get("outline") or []

        # 출력 파일 경로 기본값: <PDF이름>.rfp_compliance.xlsx
        # out_path가 지정되지 않으면 자동 생성
        if not out_path:
            # PDF 파일명에서 확장자 제거
            stem = os.path.splitext(os.path.basename(pdf_path))[0]
            # 출력 디렉토리 결정 (환경변수 > PDF 디렉토리 > 현재 디렉토리)
            out_dir = os.getenv("RFP_OUT_DIR") or os.path.dirname(pdf_path) or os.getcwd()
            out_path = os.path.join(out_dir, f"{stem}.rfp_compliance.xlsx")

        # 이 시점에서 기본적으로 RFP.pdf → RFP.rfp_compliance.xlsx 사용

        # PDF에서 텍스트 추출
        text = await self._extract_text(pdf_path)
        # 텍스트가 비어있으면 에러 반환 (OCR 필요할 수 있음)
        if not text.strip():
            return {"ok": False, "error": "PDF text empty (need OCR?)"}

        # LLM을 사용하여 요구사항 추출
        try:
            items = await self._llm_requirements(text, outline)
        except Exception as e:
            return {"ok": False, "error": f"LLM requirement error: {e}"}

        # Excel 파일로 저장
        self._save_xlsx_single(items, out_path)
        # 커버리지 갭 분석 수행
        gaps = self._coverage_gaps(outline or [], items)

        # 성공 응답 반환
        return {
            "ok": True,
            "file": out_path,  # 생성된 Excel 파일 경로
            "rows": len(items),  # 추출된 요구사항 개수
            "coverage_gaps": gaps,  # 커버리지 갭 목록
            "outline_used": outline or [],  # 사용된 목차 정보
        }


# --------------------------
# gRPC 서버 부트스트랩
# --------------------------

async def _amain():
    """
    ComplianceMatrixAgent의 gRPC 서버 실행
    - 환경변수에서 주소를 읽어 서버 시작
    - health.ping과 compliance.build 토픽 등록
    """
    # 환경변수에서 서버 주소 읽기 (기본값: 127.0.0.1:6052)
    addr = os.getenv("RFP_COMPLIANCE_ADDR", "127.0.0.1:6052")
    # 호스트와 포트 분리
    host, port_str = addr.rsplit(":", 1)

    # gRPC 서버 및 에이전트 인스턴스 생성
    server = GrpcServer(host=host, port=int(port_str))
    agent = ComplianceMatrixAgent()

    # 헬스체크 핸들러 정의
    async def _health(_):
        return {"ok": True, "agent": agent.name}

    # 토픽별 핸들러 등록
    server.register("health.ping", _health)  # 헬스체크
    server.register("compliance.build", agent._handle)  # 컴플라이언스 매트릭스 생성

    # 서버 시작 로그 출력
    print(f"[compliance] starting server at {addr}", flush=True)

    # 서버 시작 및 종료 대기
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_amain())
