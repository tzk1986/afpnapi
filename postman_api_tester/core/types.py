"""共享类型定义。"""

from typing import Any, Callable, Dict, List, TypedDict


class SummaryData(TypedDict):
    total: int
    passed: int
    failed: int
    error: int
    success_rate: str
    duration: str
    start_time: str
    end_time: str
    avg_response_ms: int
    max_response_ms: int
    p95_response_ms: int


ReportJson = Dict[str, Any]
DetailsData = Dict[str, ReportJson]
IndexResultsData = List[ReportJson]
ReportMetadata = Dict[str, Any]
ProgressPayload = Dict[str, Any]
ProgressCallback = Callable[[ProgressPayload], None]


def copy_summary(summary: SummaryData) -> SummaryData:
    return {
        'total': summary['total'],
        'passed': summary['passed'],
        'failed': summary['failed'],
        'error': summary['error'],
        'success_rate': summary['success_rate'],
        'duration': summary['duration'],
        'start_time': summary['start_time'],
        'end_time': summary['end_time'],
        'avg_response_ms': summary['avg_response_ms'],
        'max_response_ms': summary['max_response_ms'],
        'p95_response_ms': summary['p95_response_ms'],
    }
