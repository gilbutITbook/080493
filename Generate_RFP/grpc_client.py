# grpc_client.py
# gRPC 클라이언트 구현: RFP 서비스용
#
# 에이전트 간 직접 통신(A2A)을 위한 공통 클라이언트입니다.
# 각 에이전트(Outline, Compliance)에서 다른 gRPC 에이전트와 통신하기 위해 사용합니다.

import json

import grpc

import rfp_pb2        # protobuf 메시지 정의
import rfp_pb2_grpc   # protobuf 서비스 정의


class GrpcClient:
    """
    gRPC 클라이언트

    - address: "host:port" 형태의 에이전트 gRPC 서버 주소
    - request(topic, payload) 으로 JSON 기반 RPC 호출
    """
    def __init__(self, address: str = "127.0.0.1:6052", timeout_sec: float = 60.0):
        # gRPC 서버 주소 및 타임아웃 설정
        self._address = address
        self._timeout = timeout_sec
        # 지연 초기화를 위한 채널과 스텁 (첫 요청 시 생성)
        self._channel: grpc.aio.Channel | None = None
        self._stub: rfp_pb2_grpc.RfpStub | None = None

    async def _ensure(self):
        """
        gRPC 채널과 스텁이 없으면 생성 (지연 초기화)
        - keepalive 옵션으로 연결 유지
        """
        if not self._channel:
            # keepalive 옵션 설정 (연결 유지)
            opts = [
                ("grpc.keepalive_time_ms", 10_000),  # 10초마다 keepalive
                ("grpc.keepalive_timeout_ms", 5_000),  # 5초 타임아웃
            ]
            # 비보안 채널 생성 (로컬 통신용)
            self._channel = grpc.aio.insecure_channel(self._address, options=opts)
            # Rfp 서비스 스텁 생성
            self._stub = rfp_pb2_grpc.RfpStub(self._channel)

    async def request(self, topic: str, payload: dict):
        """
        gRPC 요청 전송
        - topic: 요청 토픽 (예: "outline.extract", "compliance.build")
        - payload: JSON 직렬화 가능한 딕셔너리
        - 반환: {"ok": bool, ...} 형태의 응답
        """
        # 채널과 스텁이 없으면 생성
        await self._ensure()

        # gRPC 요청 메시지 생성
        # payload를 JSON 문자열로 직렬화
        req = rfp_pb2.RfpRequest(
            topic=topic,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )

        # gRPC 호출 시도
        try:
            resp = await self._stub.Call(req, timeout=self._timeout)
        except grpc.aio.AioRpcError as e:
            # gRPC 에러 처리 (네트워크, 타임아웃 등)
            return {"ok": False, "error": f"grpc {e.code().name}: {e.details()}"}
        except Exception as e:
            # 기타 예외 처리
            return {"ok": False, "error": f"grpc exception: {e}"}

        # 응답이 실패인 경우
        if not resp.ok:
            return {"ok": False, "error": resp.error or "unknown error"}

        # 응답 JSON 파싱
        try:
            return json.loads(resp.result_json or "{}")
        except Exception as e:
            # JSON 파싱 실패 처리
            return {"ok": False, "error": f"result_json invalid: {e}"}
