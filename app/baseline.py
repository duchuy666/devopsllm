"""Deterministic development B0. Observed context only; no labels, RAG or API."""
import re
from app.report_schema import IncidentReport

VERSION='b0-rules-0.1'


def service_name(pod):
    return re.sub(r'-[a-z0-9]{8,10}-[a-z0-9]{5}$','',pod or 'unknown')


def diagnose_rules(context):
    metrics=context.get('metrics',[]);candidates=[]
    def add(score,service,fault,cause,evidence,rationale):
        candidates.append((score,{'service':service,'fault_type':fault,'root_cause':cause,
            'evidence_ids':evidence,'rationale':rationale}))
    for row in metrics:
        kind=row['metric'];pod=row.get('pod');eid=row['evidence_id']
        if kind in ('cpu','memory') and pod:
            limit=next((m for m in metrics if m['metric']==kind+'_limit' and m.get('pod')==pod and m.get('max',0)>0),None)
            if limit:
                ratio=row['max']/limit['max']
                if ratio>=.75:
                    add(min(ratio,1),service_name(pod),'Resource Exhaustion',
                        f'{kind.upper()} đạt ít nhất 75% limit quan sát được.',[eid,limit['evidence_id']],
                        f'Peak/limit = {ratio:.1%}; đây là giả thuyết áp lực tài nguyên, chưa xác nhận nguyên nhân gốc.')
        elif kind=='ready' and pod and row['min']<.5:
            add(1,service_name(pod),'Pod Failure','Có mẫu Pod không Ready trong cửa sổ.',[eid],
                'Cần kiểm tra lifecycle và rollout; trạng thái này cũng có thể xuất hiện khi khởi động bình thường.')
        elif kind=='restarts' and pod and row['max']>row['min']:
            add(1,service_name(pod),'Pod Failure','Restart counter tăng trong cửa sổ.',[eid],
                'Counter tăng là tín hiệu gián đoạn container; chưa xác nhận lý do restart.')
        elif kind=='latency_mean' and row['max']>.25:
            add(.5,row.get('service') or service_name(pod),'Unknown',
                f'Route {row.get("route") or "unknown"} có latency mean vượt 250 ms.',[eid],
                'Latency cao không đủ phân biệt network delay/loss với lỗi ứng dụng; B0 không suy diễn directed edge.')
    candidates.sort(key=lambda pair:(-pair[0],pair[1]['service'],pair[1]['fault_type'],pair[1]['evidence_ids']))
    hypotheses=[];seen=set()
    for _,item in candidates:
        key=(item['service'],item['fault_type'])
        if key not in seen:hypotheses.append(item);seen.add(key)
        if len(hypotheses)==3:break
    return IncidentReport(incident_id=context['incident_id'],
        status='hypotheses_available' if hypotheses else 'insufficient_evidence',hypotheses=hypotheses,
        recommended_actions=['Đối chiếu metric với log/trace và kiểm tra trạng thái triển khai trước khi can thiệp.'],
        missing_evidence=['B0 không xác nhận root cause hoặc phân biệt delay/loss chỉ từ latency.',
                          'Không có confidence đã hiệu chỉnh; trường confidence đặt 0.'],confidence=0).model_dump()
