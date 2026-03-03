# metrics.py
"""
성능 모니터링 및 메트릭 수집 모듈
각 에이전트의 실행 시간, 토큰 사용량, 비용 등을 추적합니다.
"""
import time
from typing import Any, Dict, Optional


class PerformanceMonitor:
    """
    성능 메트릭을 수집하고 관리하는 클래스
    각 에이전트의 실행 시간, 토큰 사용량, 비용 추정 등을 기록합니다.
    """
    
    def __init__(self):
        """
        성능 모니터 초기화
        메트릭을 저장할 딕셔너리를 생성합니다.
        """
        self.metrics: Dict[str, Any] = {}

    def start_timer(self, name: str) -> float:
        """
        타이머를 시작하고 현재 시간을 반환합니다.
        
        Args:
            name: 타이머 이름 (현재는 사용되지 않지만 향후 확장 가능)
            
        Returns:
            시작 시간 (time.time() 값)
        """
        return time.time()

    def record_metrics(
        self,
        name: str,
        start_time: float,
        token_usage: Optional[Dict[str, Any]] = None,
        cost_estimate: float = 0.0,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """
        메트릭을 기록합니다.
        실행 시간, 토큰 사용량, 비용 추정, 성공 여부 등을 저장합니다.
        
        Args:
            name: 메트릭 이름 (예: "Draft", "Critic")
            start_time: start_timer()에서 반환된 시작 시간
            token_usage: 토큰 사용량 정보 딕셔너리
            cost_estimate: 비용 추정값
            success: 작업 성공 여부
            error_message: 에러 메시지 (실패 시)
        """
        # 경과 시간 계산
        elapsed = time.time() - start_time
        # 메트릭 저장
        self.metrics[name] = {
            "elapsed": elapsed,
            "token_usage": token_usage,
            "cost_estimate": cost_estimate,
            "success": success,
            "error_message": error_message,
        }

