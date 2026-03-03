# =============================================================
# File: retriever.py
# Port: 6002
# Role: VOC CSV에서 필터 기반 텍스트 검색 (OR 검색)
# =============================================================

# ============ 표준 라이브러리 및 외부 패키지 임포트 ============
# 비동기 프로그래밍 지원
import asyncio
# 운영체제 관련 기능 (파일 존재 여부 확인 등)
import os
# gRPC 라이브러리 (비동기 서버 통신)
import grpc
# CSV 파일 읽기/쓰기 지원
import csv

# ============ Protocol Buffers 생성 파일 임포트 ============
# voc.proto 파일로부터 생성된 메시지 및 서비스 정의
import voc_pb2
import voc_pb2_grpc


# ============ Retriever Agent 비즈니스 로직 ============
# CSV 파일에서 필터 조건에 맞는 VOC 데이터를 검색하는 에이전트
# OR 검색 방식: 필터 키워드 중 하나라도 포함되면 결과에 포함됩니다
# -------------------------------------------------------------
# Retriever Agent Logic (OR 검색)
# -------------------------------------------------------------
class RetrieverAgent:
    """
    filters 기반으로 VOC CSV에서 텍스트를 추출하는 Agent.
    OR 검색(any): filters 중 하나라도 포함되면 결과로 포함.
    max_items 개수만큼만 반환한다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        RetrieverAgent 인스턴스를 초기화합니다.
        다음 에이전트(Summarizer)의 엔드포인트를 설정합니다.
        """
        # ============ 다음 에이전트 엔드포인트 설정 ============
        # Summarizer 에이전트의 엔드포인트를 환경변수에서 읽어옵니다
        self.summarizer_endpoint = os.environ.get("SUMMARIZER_ENDPOINT", "localhost:6003")

    # ============ 검색 실행 메서드 ============
    async def run(self, csv_path: str, filters: list[str], max_items: int) -> list[str]:
        """
        CSV 파일에서 필터 조건에 맞는 VOC 텍스트를 검색합니다.
        
        OR 검색 방식: filters 리스트의 키워드 중 하나라도 포함되면 결과에 포함됩니다.
        검색은 대소문자를 구분하지 않습니다 (소문자로 변환하여 비교).
        
        Args:
            csv_path: 검색할 CSV 파일 경로
            filters: 필터링할 키워드 리스트 (빈 리스트면 필터링 없음)
            max_items: 최대 반환할 항목 수 (1~500 범위로 제한)
            
        Returns:
            list[str]: 검색된 VOC 텍스트 리스트
            
        Raises:
            FileNotFoundError: CSV 파일이 존재하지 않을 때
        """
        # ============ CSV 파일 존재 여부 확인 ============
        # 파일이 없으면 조기 종료하여 불필요한 처리를 방지합니다
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        # ============ 필터 전처리 ============
        # 필터 키워드들을 소문자로 변환하고 앞뒤 공백을 제거합니다
        # 빈 문자열은 제외합니다
        filters = [f.lower().strip() for f in (filters or []) if f.strip()]

        # ============ 필터 사용 여부 결정 ============
        # 빈 필터 리스트는 필터링을 사용하지 않음을 의미합니다
        # 전체 반환 모드가 아니라 필터가 없으면 모든 행을 반환합니다
        use_filter = len(filters) > 0

        # ============ max_items 검증 및 제한 ============
        # max_items를 정수로 변환하고 유효한 범위로 제한합니다
        try:
            max_items = int(max_items)
        except Exception:
            # 변환 실패 시 기본값 사용
            max_items = 30

        # ============ 범위 제한 ============
        # 최소값: 30 (0 이하일 때)
        if max_items <= 0:
            max_items = 30
        # 최대값: 500 (너무 많은 항목 반환 방지)
        if max_items > 500:
            max_items = 500

        # ============ 결과 리스트 초기화 ============
        results = []

        # ============ CSV 파일 읽기 및 필터링 ============
        # UTF-8 인코딩으로 CSV 파일을 열어 한글을 올바르게 처리합니다
        with open(csv_path, "r", encoding="utf-8") as fp:
            csv_reader = csv.reader(fp)
            # ============ 각 행 처리 ============
            for row in csv_reader:
                # ============ 행을 문자열로 변환 ============
                # CSV의 각 열을 공백으로 결합하여 하나의 문자열로 만듭니다
                # 소문자로 변환하여 대소문자 구분 없이 검색합니다
                line = " ".join(row).lower()

                # ============ OR 조건 필터링 ============
                # 필터를 사용하지 않거나, 필터 키워드 중 하나라도 포함되면 결과에 추가합니다
                # any() 함수는 리스트의 요소 중 하나라도 조건을 만족하면 True를 반환합니다
                if not use_filter or any(f in line for f in filters):
                    # 원본 행을 공백으로 결합하여 결과에 추가합니다 (소문자 변환 전 원본 사용)
                    results.append(" ".join(row))

                    # ============ 최대 개수 도달 시 조기 종료 ============
                    # max_items 개수에 도달하면 더 이상 검색하지 않고 반복문을 종료합니다
                    if len(results) >= max_items:
                        break

        # ============ 결과 반환 ============
        return results


# ============ gRPC 서비스 구현 ============
# Protocol Buffers로 정의된 서비스를 구현하는 클래스
# 클라이언트의 RPC 요청을 받아 RetrieverAgent의 비즈니스 로직을 실행합니다
# -------------------------------------------------------------
# gRPC Servicer
# -------------------------------------------------------------
class RetrieverServicer(voc_pb2_grpc.RetrieverServicer):
    """
    Retriever gRPC 서비스를 구현하는 클래스입니다.
    
    voc_pb2_grpc.RetrieverServicer를 상속받아
    Protocol Buffers로 정의된 RPC 메서드들을 구현합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        RetrieverServicer 인스턴스를 초기화합니다.
        비즈니스 로직을 담당하는 RetrieverAgent를 생성합니다.
        """
        self.agent = RetrieverAgent()

    # ============ Retrieve RPC 구현 ============
    async def Retrieve(self, request, context):
        """
        Retrieve RPC를 구현합니다.
        
        클라이언트로부터 CSV 경로, 필터, 최대 항목 수를 받아
        필터 조건에 맞는 VOC 텍스트를 검색하고,
        Summarizer를 직접 호출하여 다음 단계로 진행합니다.
        
        Args:
            request: RetrieveReq 메시지 (csv_path, filters, max_items, task 포함)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            RetrieveRes: 검색된 텍스트 리스트를 포함한 응답 메시지
        """
        try:
            # ============ 요청 파라미터 추출 ============
            csv_path = request.csv_path        # CSV 파일 경로
            filters = list(request.filters)    # 필터 키워드 리스트 (gRPC repeated 필드를 리스트로 변환)
            max_items = request.max_items       # 최대 검색 항목 수
            task = getattr(request, 'task', 'both')  # 작업 유형 (proto에 없으면 기본값 사용)

            # ============ 검색 실행 ============
            # 에이전트의 run 메서드를 호출하여 VOC 데이터를 검색합니다
            texts = await self.agent.run(csv_path, filters, max_items)

            # ============ Summarizer 직접 호출 ============
            # Retriever가 Summarizer를 직접 호출하여 다음 단계로 진행합니다
            async with grpc.aio.insecure_channel(self.agent.summarizer_endpoint) as ch:
                stub = voc_pb2_grpc.SummarizerStub(ch)
                sres = await stub.MakeCandidates(
                    voc_pb2.SummarizeReq(
                        texts=texts,
                        max_items=max_items,
                        n=3,
                    ),
                    timeout=180.0
                )
            
            # ============ 응답 메시지 생성 및 반환 ============
            # 검색된 텍스트를 gRPC 응답 메시지로 감싸서 반환합니다
            # (실제로는 Summarizer가 다음 단계를 호출하므로 여기서는 texts만 반환)
            return voc_pb2.RetrieveRes(texts=texts)

        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(
                grpc.StatusCode.INTERNAL,  # 내부 서버 오류 상태 코드
                f"Retriever error: {e}"   # 에러 메시지
            )


# ============ gRPC 서버 실행 함수 ============
# 이 모듈을 직접 실행할 때 gRPC 서버를 시작하는 함수
# -------------------------------------------------------------
# gRPC Server
# -------------------------------------------------------------
async def serve():
    """
    Retriever gRPC 서버를 시작합니다.
    
    환경변수 RETRIEVER_ENDPOINT에서 엔드포인트를 읽어옵니다.
    기본값은 "0.0.0.0:6002"입니다 (모든 네트워크 인터페이스의 6002 포트).
    """
    # ============ 엔드포인트 설정 ============
    # 환경변수에서 엔드포인트를 읽어오고, 없으면 기본값을 사용합니다
    endpoint = os.environ.get("RETRIEVER_ENDPOINT", "0.0.0.0:6002")

    # ============ gRPC 서버 생성 ============
    # 비동기 gRPC 서버 인스턴스를 생성합니다
    server = grpc.aio.server()
    # ============ 서비스 등록 ============
    # RetrieverServicer를 서버에 등록하여 RPC 요청을 처리할 수 있도록 합니다
    voc_pb2_grpc.add_RetrieverServicer_to_server(RetrieverServicer(), server)
    # ============ 포트 바인딩 ============
    # 서버를 지정된 엔드포인트에 바인딩합니다 (TLS 없이)
    server.add_insecure_port(endpoint)

    # ============ 서버 시작 로그 ============
    # 서버가 시작되었음을 콘솔에 출력합니다
    print(f"[Retriever] gRPC server started at {endpoint}")

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
