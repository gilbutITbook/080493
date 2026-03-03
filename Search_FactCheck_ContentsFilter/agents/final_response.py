# 최종 응답 생성 에이전트 모듈
# 모든 검증 결과를 종합하여 최종 응답을 생성합니다.

import os, sys
# 상위 디렉토리를 Python 경로에 추가하여 agents_pb2 모듈을 import할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import asyncio
import agents_pb2
import agents_pb2_grpc

class FinalizerService(agents_pb2_grpc.FinalizerServiceServicer):
    """
    최종 응답 생성 서비스 클래스
    gRPC 서비스로 구현되어 있으며, 모든 검증 결과를 종합하여 최종 응답을 생성합니다.
    """
    async def Finalize(self, request, context):
        """
        최종 응답 생성 메서드
        환각 필터 결과와 팩트체크 결과를 종합하여 최종 응답을 생성합니다.
        """
        # 요청에서 답변, 환각 분석 결과, 팩트 데이터 추출
        answer = request.answer
        hallu = request.hallu
        fact = request.fact_data

        # 환각 분석 결과에서 위험도와 팩트 검증 상태 추출
        risk = hallu.overall_risk
        fact_status = hallu.fact_status

        # 위험도와 팩트 검증 상태에 따라 신뢰도 메시지 생성
        if risk=="low" and fact_status=="verified":
            # 낮은 위험도와 검증 완료된 경우
            msg = "팩트 확인 완료 - 신뢰도 높음"
        elif risk=="medium":
            # 중간 위험도인 경우
            msg = "주의 필요 - 부분 검증"
        else:
            # 높은 위험도이거나 검증되지 않은 경우
            msg = "신뢰도 낮음"

        # 참고 소스 URL 리스트 생성 (최대 3개까지)
        src = "\n".join(f"- {s}" for s in fact.sources[:3])

        # 최종 응답 구성
        # 신뢰도 메시지, 응답 내용, 환각 수준, 참고 소스를 포함합니다
        final = (
            f"{msg}\n\n"
            f"[응답]\n{answer}\n\n"
            f"Hallucination: {hallu.hallucination_level}\n\n"
            f"참고 소스:\n{src}"
        )

        # gRPC 응답 반환
        return agents_pb2.FinalizeResponse(final_answer=final)

async def serve():
    """
    gRPC 서버 실행 함수
    최종 응답 생성 서비스를 gRPC 서버로 실행합니다.
    """
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # FinalizerService를 서버에 등록
    agents_pb2_grpc.add_FinalizerServiceServicer_to_server(
        FinalizerService(), server
    )
    # 포트 50055에서 서비스 시작 (모든 인터페이스에서 수신)
    server.add_insecure_port("[::]:50055")
    await server.start()
    print("FinalizerService ON 50055")
    # 서버 종료 대기
    await server.wait_for_termination()

if __name__=="__main__":
    # 직접 실행 시 서버 시작
    asyncio.run(serve())
