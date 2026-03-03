# ================================================
# File: interpreter.py
# Role: 자연어 질문 해석 에이전트 + gRPC 서버 (a2a.Interpreter)
# Port (default bind): 0.0.0.0:6001
# ================================================

# ============ 표준 라이브러리 및 타입 힌트 ============
# Python 3.7+ 호환성을 위한 annotations 가져오기 (타입 힌트 지연 평가)
from __future__ import annotations

# 운영체제 관련 기능 (환경변수 읽기 등)
import os
# 비동기 프로그래밍 지원
import asyncio
# 데이터 클래스 정의 (타입 안전한 구조체)
from dataclasses import dataclass
# 타입 힌트를 위한 타입 정의들
from typing import List, Optional

# ============ Protocol Buffers 생성 파일 임포트 ============
# voc.proto 파일로부터 생성된 메시지 및 서비스 정의
import grpc
import voc_pb2
import voc_pb2_grpc

# ============ 프로젝트 내부 모듈 임포트 ============
# 시스템 설정 및 기본값
from utils.settings import DEFAULT_CSV, openai_client, MODEL_SUMMARY
# JSON 추출 유틸리티 함수
from utils.json_utils import extract_json


# ============ 비즈니스 로직 ============
# 자연어 질의를 구조화된 파라미터로 변환하는 에이전트
# --------------------------------
# 비즈니스 로직
# --------------------------------

# ============ 자연어 의도 데이터 클래스 ============
@dataclass
class NLIntent:
    """
    자연어 질문을 해석한 결과를 담는 데이터 클래스입니다.
    
    사용자의 자연어 질의를 분석하여 구조화된 파라미터로 변환한 결과를 저장합니다.
    """
    task: str = "both"                # 수행할 작업 유형: "summary" | "policy" | "both"
    filters: List[str] | None = None  # 검색 키워드들 (None이면 필터링 없음)
    max_items: int = 30               # 최대 VOC 개수 (기본값: 30)
    csv_path: str = DEFAULT_CSV       # 사용할 CSV 경로 (기본값: settings.DEFAULT_CSV)


# ============ 자연어 해석 에이전트 클래스 ============
class NLInterpreterAgent:
    """
    OpenAI LLM을 사용하여 사용자의 자연어 질문을 분석하는 에이전트입니다.
    
    사용자가 "상담 대기 시간 관련 불만 분석해줘"와 같은 자연어 질의를 입력하면,
    이를 구조화된 파라미터(task, filters, max_items, csv_path)로 변환합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        NLInterpreterAgent 인스턴스를 초기화합니다.
        
        Raises:
            RuntimeError: OpenAI 클라이언트가 설정되지 않았을 때
        """
        # ============ OpenAI 클라이언트 검증 ============
        # OpenAI 클라이언트가 설정되지 않았으면 에러를 발생시킵니다
        if not openai_client:
            raise RuntimeError("OpenAI client is not configured")
        # ============ 클라이언트 저장 ============
        # OpenAI 클라이언트를 인스턴스 변수로 저장합니다
        self.client = openai_client
        # ============ 다음 에이전트 엔드포인트 설정 ============
        # Retriever 에이전트의 엔드포인트를 환경변수에서 읽어옵니다
        self.retriever_endpoint = os.environ.get("RETRIEVER_ENDPOINT", "localhost:6002")

    # ============ 자연어 파싱 메서드 ============
    async def parse(self, question: str, default_csv: Optional[str] = None) -> NLIntent:
        """
        자연어 질문을 받아 구조화된 의도(intent)를 추출합니다.
        
        LLM을 사용하여 자연어 질의를 분석하고, task, filters, max_items, csv_path를 추출합니다.
        
        Args:
            question: 사용자의 자연어 질의 (예: "상담 대기 시간 관련 불만 분석")
            default_csv: 기본 CSV 경로 (None이면 settings.DEFAULT_CSV 사용)
            
        Returns:
            NLIntent: 파싱된 의도 정보를 담은 데이터 클래스
        """
        # ============ 프롬프트 구성 ============
        # LLM에게 자연어 질의를 구조화된 JSON으로 변환하도록 지시하는 프롬프트를 작성합니다
        prompt = f"""
당신은 VOC 분석을 위한 질의 해석기입니다.
사용자의 질문을 보고 다음 네 가지 값을 JSON으로만 출력하세요.

- task: "summary", "policy", 또는 "both"
- filters: 의미 있는 핵심 키워드 배열 (예: ["앱 오류", "대기 시간"])
- max_items: 10~100 범위의 정수
- csv_path: 사용자가 별도로 언급한 CSV 경로가 있으면 그 경로, 없으면 default_csv 사용

반드시 아래 JSON 형식만 출력하세요. 설명 문장은 쓰지 마세요.

{{
  "task": "...",
  "filters": ["...", "..."],
  "max_items": 30,
  "csv_path": "..."
}}

사용자 질문:
{question}
"""
        # ============ OpenAI Responses API 호출 ============
        # OpenAI의 Responses API를 사용하여 자연어 질의를 구조화된 JSON으로 변환합니다
        # responses.create는 최신 OpenAI API 방식입니다
        resp = await self.client.responses.create(
            model=MODEL_SUMMARY,  # 요약용 모델 사용
            input=prompt,          # 프롬프트 전달
        )

        # ============ 응답 파싱 ============
        # responses.create 응답 파싱 (output[0].content[0].text 형태)
        # 응답 구조가 복잡하므로 안전하게 접근합니다
        try:
            text = resp.output[0].content[0].text
        except Exception:
            # 파싱 실패 시 빈 문자열로 처리합니다
            text = ""

        # ============ JSON 추출 ============
        # LLM 응답에서 JSON 블록을 추출합니다
        # extract_json은 마크다운 코드 블록이나 중괄호 블록에서 JSON을 찾습니다
        data = extract_json(text) or {}

        # ============ task 파라미터 처리 ============
        # 작업 유형을 추출하고 유효성을 검증합니다
        task = str(data.get("task") or "both")
        # 유효한 값이 아니면 기본값 "both"를 사용합니다
        if task not in ("summary", "policy", "both"):
            task = "both"

        # ============ filters 파라미터 처리 ============
        # 필터 키워드 리스트를 추출합니다
        filters = data.get("filters") or []
        # 리스트가 아니면 빈 리스트로 변환합니다
        if not isinstance(filters, list):
            filters = []

        # ============ max_items 파라미터 처리 ============
        # 최대 항목 수를 추출하고 유효한 범위로 제한합니다
        try:
            max_items = int(data.get("max_items") or 30)
        except Exception:
            # 변환 실패 시 기본값 사용
            max_items = 30
        # 범위 제한: 최소 5, 최대 200
        max_items = max(5, min(200, max_items))

        # ============ csv_path 파라미터 처리 ============
        # CSV 경로를 추출하고 기본값 처리를 합니다
        # LLM이 "default_csv" 같은 literal을 넣는 경우가 있어 방어 로직 추가
        raw_csv = str(data.get("csv_path") or "").strip()
        base_csv = default_csv or DEFAULT_CSV

        # ============ CSV 경로 최종 결정 ============
        # 빈 문자열이거나 "default_csv" 문자열이면 기본 경로를 사용합니다
        if not raw_csv or raw_csv.lower() == "default_csv":
            csv_path = base_csv
        else:
            # 그 외의 경우 LLM이 제공한 경로를 사용합니다
            csv_path = raw_csv

        # ============ NLIntent 객체 생성 및 반환 ============
        # 파싱된 모든 정보를 NLIntent 객체로 만들어 반환합니다
        return NLIntent(
            task=task,
            filters=filters,
            max_items=max_items,
            csv_path=csv_path,
        )


# ============ gRPC 서비스 구현 ============
# Protocol Buffers로 정의된 서비스를 구현하는 클래스
# 클라이언트의 RPC 요청을 받아 NLInterpreterAgent의 비즈니스 로직을 실행합니다
# --------------------------------
# gRPC Servicer
# --------------------------------

class InterpreterServicer(voc_pb2_grpc.InterpreterServicer):
    """
    a2a.Interpreter gRPC 서비스를 구현하는 클래스입니다.
    
    voc_pb2_grpc.InterpreterServicer를 상속받아
    Protocol Buffers로 정의된 RPC 메서드들을 구현합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        InterpreterServicer 인스턴스를 초기화합니다.
        비즈니스 로직을 담당하는 NLInterpreterAgent를 생성합니다.
        """
        self.agent = NLInterpreterAgent()

    # ============ ParseQuestion RPC 구현 ============
    async def ParseQuestion(self, request, context):
        """
        ParseQuestion RPC를 구현합니다.
        
        클라이언트로부터 자연어 질의를 받아 구조화된 의도로 변환하고,
        Retriever를 직접 호출하여 전체 파이프라인을 시작합니다.
        
        Args:
            request: ParseQuestionReq 메시지 (question, default_csv 포함)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            ParseQuestionRes: 파싱된 의도 정보를 포함한 응답 메시지
        """
        try:
            # ============ 자연어 파싱 ============
            # 에이전트의 parse 메서드를 호출하여 자연어 질의를 구조화된 의도로 변환합니다
            intent: NLIntent = await self.agent.parse(
                question=request.question,              # 자연어 질의
                default_csv=request.default_csv or None, # 기본 CSV 경로
            )
            
            # ============ Retriever 직접 호출 ============
            # Interpreter가 Retriever를 직접 호출하여 파이프라인을 시작합니다
            # Retriever가 다음 에이전트(Summarizer)를 호출하므로 여기서는 호출만 수행
            async with grpc.aio.insecure_channel(self.agent.retriever_endpoint) as ch:
                stub = voc_pb2_grpc.RetrieverStub(ch)
                rres = await stub.Retrieve(
                    voc_pb2.RetrieveReq(
                        csv_path=intent.csv_path,
                        filters=intent.filters or [],
                        max_items=intent.max_items,
                    ),
                    timeout=180.0
                )
            # Retriever가 Summarizer를 호출하므로 여기서는 결과를 기다리지 않음
            
            # ============ 응답 메시지 생성 및 반환 ============
            # 파싱된 의도를 gRPC 응답 메시지로 감싸서 반환합니다
            # (실제로는 Retriever가 다음 단계를 호출하므로 여기서는 intent만 반환)
            return voc_pb2.ParseQuestionRes(
                task=intent.task,                    # 작업 유형
                filters=intent.filters or [],        # 필터 키워드 리스트
                max_items=intent.max_items,          # 최대 항목 수
                csv_path=intent.csv_path,            # CSV 파일 경로
            )
        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(grpc.StatusCode.INTERNAL, f"Interpreter error: {e}")


# ============ gRPC 서버 실행 함수 ============
# 이 모듈을 직접 실행할 때 gRPC 서버를 시작하는 함수
# --------------------------------
# gRPC Server Runner
# --------------------------------

async def serve() -> None:
    """
    Interpreter gRPC 서버를 시작합니다.
    
    환경변수 INTERPRETER_BIND에서 엔드포인트를 읽어옵니다.
    기본값은 "0.0.0.0:6001"입니다 (모든 네트워크 인터페이스의 6001 포트).
    """
    # ============ 엔드포인트 설정 ============
    # 환경변수에서 엔드포인트를 읽어오고, 없으면 기본값을 사용합니다
    bind = os.environ.get("INTERPRETER_BIND", "0.0.0.0:6001")

    # ============ gRPC 서버 생성 ============
    # 비동기 gRPC 서버 인스턴스를 생성합니다
    server = grpc.aio.server()
    # ============ 서비스 등록 ============
    # InterpreterServicer를 서버에 등록하여 RPC 요청을 처리할 수 있도록 합니다
    voc_pb2_grpc.add_InterpreterServicer_to_server(InterpreterServicer(), server)
    # ============ 포트 바인딩 ============
    # 서버를 지정된 엔드포인트에 바인딩합니다 (TLS 없이)
    server.add_insecure_port(bind)

    # ============ 서버 시작 로그 ============
    # 서버가 시작되었음을 콘솔에 출력합니다
    print(f"[Interpreter] gRPC server started on {bind}")
    # ============ 서버 시작 및 대기 ============
    # 서버를 시작하고 종료 신호를 받을 때까지 대기합니다
    await server.start()
    # 서버가 종료될 때까지 무한 대기합니다 (Ctrl+C로 종료 가능)
    await server.wait_for_termination()


# ============ 메인 실행 블록 ============
# 스크립트가 직접 실행될 때만 서버를 시작합니다
if __name__ == "__main__":
    # asyncio.run()을 사용하여 비동기 서버를 실행합니다
    asyncio.run(serve())
