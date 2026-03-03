# ==============================================================
# File: evaluator.py
# Port: 6004
# Role: 요약 후보 평가 에이전트 (독립 실행 gRPC 서버)
# ==============================================================

# ============ 표준 라이브러리 및 외부 패키지 임포트 ============
# 비동기 프로그래밍 지원
import asyncio
# 운영체제 관련 기능 (환경변수 읽기 등)
import os
# gRPC 라이브러리 (비동기 서버 통신)
import grpc
# JSON 데이터 처리
import json
# Protocol Buffers 생성 파일 임포트
import voc_pb2
import voc_pb2_grpc

# ============ 프로젝트 내부 모듈 임포트 ============
# OpenAI Chat API를 사용하기 위한 래퍼 클래스
from llm_wrappers.openai_chat import OpenAIChat
# JSON 추출 유틸리티 함수
from utils.json_utils import extract_json


# ============ Evaluator Agent 비즈니스 로직 ============
# 여러 요약 후보를 평가하여 최적의 요약을 선택하는 에이전트
# --------------------------------------------------------------
# Evaluator Agent (비즈니스 로직)
# --------------------------------------------------------------
class EvaluatorAgent:
    """
    여러 개의 요약 후보를 비교 평가하여
    가장 높은 품질의 요약(winner)을 선택하고
    각 후보별 점수를 JSON으로 반환한다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        EvaluatorAgent 인스턴스를 초기화합니다.
        LLM 래퍼를 인스턴스 변수로 저장하여 재사용합니다.
        """
        # 클래스 변수가 아닌 인스턴스 변수로 생성해야 각 요청마다 독립적인 상태를 유지할 수 있습니다
        self.llm = OpenAIChat()
        # 다음 에이전트 엔드포인트 설정
        self.critic_endpoint = os.environ.get("CRITIC_ENDPOINT", "localhost:6005")

    # ============ 요약 후보 평가 메서드 ============
    async def evaluate(self, task: str, candidates: dict[str, str]):
        """
        후보 요약문을 task 기준으로 평가합니다.
        
        여러 요약 후보를 비교하여 가장 품질이 높은 요약을 선택하고,
        각 후보별 점수를 반환합니다.
        
        Args:
            task: 평가 기준이 되는 작업 유형 ("summary", "policy", "both")
            candidates: 평가할 요약 후보 딕셔너리 (키: S0, S1, S2 등, 값: 요약 텍스트)
            
        Returns:
            dict: winner(승자 키)와 scores(각 후보별 점수 딕셔너리)를 포함한 딕셔너리
        """
        # ============ 후보 포맷팅 ============
        # 각 후보를 "[키]\n값" 형식으로 포맷팅하여 프롬프트에 포함합니다
        items = "\n\n".join([f"[{k}]\n{v}" for k, v in candidates.items()])

        # ============ 프롬프트 구성 ============
        # LLM에게 후보들을 평가하고 승자를 선택하도록 지시하는 프롬프트를 작성합니다
        prompt = f"""
다음은 VOC 요약 후보들이다.  
주어진 작업(task="{task}") 기준으로 각 후보를 1~10 점수로 평가하고  
가장 좋은 후보를 winner로 선택해줘.

후보들:
{items}

출력 JSON 형식 예시:
{{
  "winner": "1",
  "scores": {{
    "1": 8.5,
    "2": 7.1,
    "3": 9.2
  }}
}}
"""

        # ============ LLM 호출 ============
        # 핵심: 절대 complete(), generate() 등을 쓰지 않는다.
        # OpenAIChat 래퍼의 __call__ 메서드를 사용하여 LLM을 호출합니다
        result = await self.llm(prompt)

        # ============ JSON 추출 ============
        # LLM 응답에서 JSON 블록을 추출합니다
        data = extract_json(result) or {}

        # ============ JSON 파싱 실패 처리 ============
        # JSON 파싱 실패 시 기본값을 반환합니다
        # 첫 번째 후보를 승자로 선택하고 모든 후보에 5.0 점수를 부여합니다
        if not isinstance(data, dict):
            return {
                "winner": list(candidates.keys())[0],  # 첫 번째 후보를 승자로 선택
                "scores": {k: 5.0 for k in candidates.keys()}  # 모든 후보에 중간 점수 부여
            }

        # ============ 결과 반환 ============
        # 파싱된 데이터에서 winner와 scores를 추출하여 반환합니다
        # 값이 없으면 기본값을 사용합니다
        return {
            "winner": data.get("winner", list(candidates.keys())[0]),  # 승자 키 (기본값: 첫 번째 후보)
            "scores": data.get("scores", {})  # 점수 딕셔너리 (기본값: 빈 딕셔너리)
        }



# ============ gRPC 서비스 구현 ============
# Protocol Buffers로 정의된 서비스를 구현하는 클래스
# 클라이언트의 RPC 요청을 받아 EvaluatorAgent의 비즈니스 로직을 실행합니다
# --------------------------------------------------------------
# gRPC Servicer
# --------------------------------------------------------------
class EvaluatorServicer(voc_pb2_grpc.EvaluatorServicer):
    """
    Evaluator gRPC 서비스를 구현하는 클래스입니다.
    
    voc_pb2_grpc.EvaluatorServicer를 상속받아
    Protocol Buffers로 정의된 RPC 메서드들을 구현합니다.
    """

    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        EvaluatorServicer 인스턴스를 초기화합니다.
        비즈니스 로직을 담당하는 EvaluatorAgent를 생성합니다.
        """
        self.agent = EvaluatorAgent()

    # ============ Evaluate RPC 구현 ============
    async def Evaluate(self, request, context):
        """
        Evaluate RPC를 구현합니다.
        
        클라이언트로부터 작업 유형과 요약 후보들을 받아
        평가하여 승자를 선택하고,
        Critic을 직접 호출하여 다음 단계로 진행합니다.
        
        Args:
            request: EvaluateReq 메시지
              - task: 작업 유형
              - candidates: 후보 딕셔너리 (map<string, string>)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            EvaluateRes: 승자 키와 점수 정보를 포함한 응답 메시지
        """
        try:
            # ============ 후보 딕셔너리 변환 ============
            # gRPC repeated 필드를 Python 딕셔너리로 변환합니다
            candidates = dict(request.candidates.items())
            # ============ 평가 실행 ============
            # 에이전트의 evaluate 메서드를 호출하여 후보들을 평가합니다
            out = await self.agent.evaluate(
                task=request.task,        # 작업 유형
                candidates=candidates     # 평가할 후보 딕셔너리
            )
            
            # ============ 승자 요약 추출 ============
            winner_key = out["winner"]
            summary = candidates.get(winner_key, "")
            
            # ============ Critic 직접 호출 ============
            # Evaluator가 Critic을 직접 호출하여 다음 단계로 진행합니다
            async with grpc.aio.insecure_channel(self.agent.critic_endpoint) as ch:
                stub = voc_pb2_grpc.CriticStub(ch)
                cres = await stub.Review(
                    voc_pb2.ReviewReq(
                        doc=summary,
                        role="summary"
                    ),
                    timeout=180.0
                )
            
            # ============ 응답 메시지 생성 및 반환 ============
            # 평가 결과를 gRPC 응답 메시지로 감싸서 반환합니다
            # (실제로는 Critic이 다음 단계를 호출하므로 여기서는 평가 결과만 반환)
            return voc_pb2.EvaluateRes(
                winner=out["winner"],     # 승자 키
                scores_json=json.dumps(out["scores"], ensure_ascii=False)  # 점수 정보를 JSON 문자열로 변환
            )

        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(
                grpc.StatusCode.INTERNAL,  # 내부 서버 오류 상태 코드
                f"Evaluator error: {e}"   # 에러 메시지
            )


# ============ gRPC 서버 실행 함수 ============
# 이 모듈을 직접 실행할 때 gRPC 서버를 시작하는 함수
# --------------------------------------------------------------
# gRPC Server
# --------------------------------------------------------------
async def serve():
    """
    Evaluator gRPC 서버를 시작합니다.
    
    환경변수 EVALUATOR_ENDPOINT에서 엔드포인트를 읽어옵니다.
    기본값은 "0.0.0.0:6004"입니다 (모든 네트워크 인터페이스의 6004 포트).
    """
    # ============ 엔드포인트 설정 ============
    # 환경변수에서 엔드포인트를 읽어오고, 없으면 기본값을 사용합니다
    endpoint = os.environ.get("EVALUATOR_ENDPOINT", "0.0.0.0:6004")

    # ============ gRPC 서버 생성 ============
    # 비동기 gRPC 서버 인스턴스를 생성합니다
    server = grpc.aio.server()
    # ============ 서비스 등록 ============
    # EvaluatorServicer를 서버에 등록하여 RPC 요청을 처리할 수 있도록 합니다
    voc_pb2_grpc.add_EvaluatorServicer_to_server(EvaluatorServicer(), server)
    # ============ 포트 바인딩 ============
    # 서버를 지정된 엔드포인트에 바인딩합니다 (TLS 없이)
    server.add_insecure_port(endpoint)

    # ============ 서버 시작 로그 ============
    # 서버가 시작되었음을 콘솔에 출력합니다
    print(f"[Evaluator] gRPC server started on {endpoint}")
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
