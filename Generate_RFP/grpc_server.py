# grpc_server.py
# gRPC 서버 구현: RFP 서비스용
#
# rfp.proto에서 정의한 Rfp 서비스의 구현체입니다.
# JSON 기반의 요청/응답을 처리하며, topic별 핸들러를 등록해
# 다양한 RFP 분석 기능(목차 추출, 컴플라이언스 매트릭스 생성 등)을 제공합니다.

import json
from typing import Callable, Awaitable, Dict, Any

import grpc
import rfp_pb2        # protobuf 메시지 정의 (rfp.proto에서 생성)
import rfp_pb2_grpc   # protobuf 서비스 정의

# 토픽별 핸들러 타입
Handler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class RfpServicer(rfp_pb2_grpc.RfpServicer):
    """
    RFP 서비스 gRPC 서버 구현

    rfp.proto에 정의된 Rfp 서비스를 구현합니다.
    모든 요청/응답은 JSON 문자열로 직렬화하여 주고받습니다.
    """
    def __init__(self, registry: Dict[str, Handler]):
        # 토픽별 핸들러 등록부 (topic -> handler 함수)
        self._registry = registry

    async def Call(self, request, context):
        """
        gRPC Call 메서드 구현
        - 요청의 topic에 해당하는 핸들러를 찾아 실행
        - payload_json을 파싱하여 핸들러에 전달
        - 핸들러 결과를 result_json으로 직렬화하여 반환
        """
        # 요청 토픽 추출
        topic = request.topic

        # payload_json → dict 변환
        try:
            payload = json.loads(request.payload_json or "{}")
        except Exception as e:
            # JSON 파싱 실패 시 에러 응답
            return rfp_pb2.RfpResponse(ok=False, error=f"invalid payload_json: {e}")

        # 토픽에 해당하는 핸들러 찾기
        handler = self._registry.get(topic)
        if not handler:
            # 핸들러가 없으면 에러 응답
            return rfp_pb2.RfpResponse(ok=False, error=f"no handler for topic '{topic}'")

        # 핸들러 실행
        try:
            resp = await handler(payload)
            # 성공 응답: 결과를 JSON으로 직렬화
            return rfp_pb2.RfpResponse(
                ok=True,
                result_json=json.dumps(resp, ensure_ascii=False),
            )
        except Exception as e:
            # 핸들러 실행 중 예외 발생 시 에러 응답
            return rfp_pb2.RfpResponse(ok=False, error=str(e))


class GrpcServer:
    """
    가벼운 gRPC 서버 래퍼

    - register(topic, handler) 로 handler 등록
    - start() / wait_for_termination() 으로 서버 수명 관리
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 6051):
        # 서버 호스트와 포트 설정
        self._host = host
        self._port = port
        # 토픽별 핸들러 등록부 (초기화 시 빈 딕셔너리)
        self._registry: Dict[str, Handler] = {}
        # gRPC 서버 인스턴스 (start() 호출 시 생성)
        self._server: grpc.aio.Server | None = None

    def register(self, topic: str, handler: Handler):
        """
        토픽별 핸들러 등록
        - topic: 요청 토픽 문자열
        - handler: 비동기 핸들러 함수
        """
        self._registry[topic] = handler

    async def start(self):
        """
        gRPC 서버 시작
        - 비동기 gRPC 서버 생성
        - RfpServicer를 서버에 등록
        - 지정된 주소에 바인딩하고 시작
        """
        # 비동기 gRPC 서버 인스턴스 생성
        self._server = grpc.aio.server()
        # RfpServicer를 서버에 등록
        # 등록부의 핸들러들이 서비스를 통해 호출됨
        rfp_pb2_grpc.add_RfpServicer_to_server(
            RfpServicer(self._registry),
            self._server,
        )

        # 바인딩 주소 구성
        bind_addr = f"{self._host}:{self._port}"
        # 비보안 포트 추가 (로컬 통신용)
        self._server.add_insecure_port(bind_addr)
        # 이 서버는 MCP stdio 채널과 분리된 외부 프로세스로 띄우므로 print 사용 가능
        print(f"[grpc] Listening on {bind_addr}", flush=True)

        # 서버 시작
        await self._server.start()

    async def wait_for_termination(self):
        """
        서버 종료 대기
        - 서버가 종료될 때까지 대기 (Ctrl+C 등으로 종료 신호 받을 때까지)
        """
        if self._server:
            await self._server.wait_for_termination()
