"""Blinded local task UI. The assistant must never start/complete tasks for a human."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import uuid
import streamlit as st
from app.human_study import timing,study_complete,snapshot_inputs,read_inputs,study_cancelled
from app.report_schema import IncidentReport

ROOT=Path(__file__).resolve().parents[1]
PROCESS=uuid.uuid4().hex


def save(path,session):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(session,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def live_ttd():
    st.subheader('Thời gian từ cảnh báo đến báo cáo (live)')
    rows=[]
    for path in sorted(ROOT.glob('results/live-diagnoses/*/ttd.json')):
        r=json.loads(path.read_text())
        if r.get('status')!='report_generated':continue
        top=''
        result=ROOT/'results/diagnoses'/r['context_id']/r['mode']/'result.json'
        if result.exists():
            hyp=json.loads(result.read_text())['generated']['report']['hypotheses']
            if hyp:top=hyp[0]['service']+' · '+hyp[0]['fault_type']
        c=r['components_seconds']
        rows.append({'Incident':r['incident_id'],'Cấu hình':r['mode'],'Giả thuyết Top-1':top,
                     'Chờ cửa sổ sau alert (s)':round(c['alert_to_capture'],1),'Dựng context (s)':round(c['capture_to_context'],1),
                     'Truy xuất + Gemini (s)':round(c['llm_and_retrieval'],1),'Tổng (s)':round(r['ttd_seconds'],1)})
    if not rows:st.info('Chưa có lượt đo live.');return
    a,b,c=st.columns(3)
    total=[r['Tổng (s)'] for r in rows]
    a.metric('Số lượt đo',len(rows));b.metric('Trung bình (s)',round(sum(total)/len(total),1));c.metric('Nhanh nhất – chậm nhất (s)',f'{min(total)} – {max(total)}')
    st.dataframe(rows,hide_index=True,width='stretch')
    st.caption('Tính từ lúc collector nhận cảnh báo tới khi có báo cáo B3, gồm 30 giây chờ đủ cửa sổ telemetry sau cảnh báo. '
               'Lỗi CPU tiêm bằng Chaos Mesh; đây là đo live, không phải thời gian replay.')


def render_study():
    live_ttd()
    st.subheader('Đo thời gian chẩn đoán của người với đáp án ẩn')
    if study_cancelled(ROOT):
        st.caption('Phiên đo người đã được hủy trước khi bắt đầu (experiments/human-study-cancelled.json): review ca test đã mở nên không thể đo mù với cùng reviewer. Chưa có số liệu so sánh người–máy.');return
    st.caption('Phiên pilot một người, 14 ca thuộc bảy cặp cùng họ kịch bản; mỗi cặp dùng hai ca khác nhau. Không phải crossover cùng ca. Thời gian là thao tác trên context đã có sẵn, không phải live TTD.')
    plan_path=ROOT/'experiments/human-study-plan.json'
    if not plan_path.exists():st.info('Chưa có protocol phiên đo.');return
    plan=json.loads(plan_path.read_text())
    if plan['source_plan_sha256']!=hashlib.sha256((ROOT/'experiments/scenario-plan.json').read_bytes()).hexdigest():
        st.error('Scenario plan đã đổi sau đăng ký phiên đo; cần đối chiếu protocol trước khi tiếp tục.');return
    manifests=sorted((ROOT/'results/prospective-benchmark').glob('*/test/manifest.json'))
    ready=None
    for path in reversed(manifests):
        manifest=json.loads(path.read_text());by_id={c['scenario_id']:c for c in manifest['cases']}
        if all(t['scenario_id'] in by_id for t in plan['tasks']):ready=(path,by_id);break
    if ready is None:
        st.info('Đang chờ đủ observation test và gói benchmark. Chưa tạo phiên hoặc số đo người dùng.');return
    path,by_id=ready
    for task in plan['tasks']:
        case=by_id[task['scenario_id']]
        mode='B0' if task['condition']=='B0_dashboard' else 'B3'
        report_path=path.parent/case['reports'][mode]
        if not report_path.is_file():
            st.info('Đang chờ report của điều kiện được giao. Không dùng đáp án ground truth thay report.');return
        try:
            saved=json.loads(report_path.read_text())
            report=IncidentReport.model_validate(saved['generated']['report'])
            context=json.loads((path.parent/case['context_file']).read_text())
            if saved['mode']!=mode or report.incident_id!=case['context_id'] or context['incident_id']!=case['context_id']:
                raise ValueError('Context/report identity mismatch')
        except (ValueError,KeyError,TypeError,OSError):
            st.error('Report/context không hợp lệ. Giữ lỗi để điều phối xử lý trước khi đo; không tạo số đo thay thế.');return
    participant=st.text_input('Pseudonym người tham gia',key='human_participant')
    consent=st.checkbox('Tôi đồng ý ghi thời gian thao tác và chưa xem đáp án ground truth của các ca test',key='human_consent')
    if not participant.strip() or not consent:
        st.info('Người tham gia tự nhập pseudonym và xác nhận trước khi bắt đầu.');return
    participant_key=hashlib.sha256(participant.strip().encode()).hexdigest()[:16]
    session_path=ROOT/'results/human-study'/plan['study_id']/participant_key/'session.json'
    session=json.loads(session_path.read_text()) if session_path.exists() else {
        'participant_id':participant.strip(),'consent':True,'protocol_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        'completed_tasks':[],'active_task':None}
    if session['protocol_sha256']!=hashlib.sha256(plan_path.read_bytes()).hexdigest():
        st.error('Protocol đã đổi so với phiên này; không tiếp tục trộn số đo.');return
    done={t['case_opaque_id'] for t in session['completed_tasks']}
    remaining=[t for t in plan['tasks'] if t['case_opaque_id'] not in done]
    st.progress(len(done)/len(plan['tasks']),text=f'Đã hoàn thành {len(done)} / {len(plan["tasks"])} ca đo')
    if not remaining:
        st.success('Phiên đo đã kết thúc. Chưa tính correctness hoặc ROI từ số liệu chưa được review.');return
    task=remaining[0];case=by_id[task['scenario_id']];active=session.get('active_task')
    st.write('Ca ẩn danh: '+task['case_opaque_id'])
    st.write('Điều kiện: '+('Dashboard và B0 local' if task['condition']=='B0_dashboard' else 'Dashboard và báo cáo trợ lý B3'))
    if not active:
        if st.button('Bắt đầu quan sát ca này',key='start-human-'+task['case_opaque_id']):
            mode='B0' if task['condition']=='B0_dashboard' else 'B3'
            hashes=snapshot_inputs(session_path.parent/'inputs'/task['case_opaque_id'],
                path.parent/case['context_file'],path.parent/case['reports'][mode])
            session['active_task']={**task,'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'start_monotonic':time.monotonic(),'server_process':PROCESS,'input_sha256':hashes}
            save(session_path,session);st.rerun()
        return
    if active['case_opaque_id']!=task['case_opaque_id'] or active['server_process']!=PROCESS:
        st.error('Phiên đang đo bị gián đoạn bởi server restart. Giữ log gốc và điều phối xử lý, không tự dựng thời gian.');return
    try:
        context,saved_report=read_inputs(session_path.parent/'inputs'/task['case_opaque_id'],active['input_sha256'])
    except (ValueError,KeyError,OSError):
        st.error('Bản chụp đầu vào phiên đo không khớp. Giữ log gốc để điều phối xử lý.');return
    for key,label in [('metrics','Metric'),('logs','Log template'),('traces','Trace')]:
        with st.expander(label,expanded=key=='metrics'):
            st.json(context[key],expanded=False)
    mode='B0' if task['condition']=='B0_dashboard' else 'B3'
    report=saved_report['generated']['report']
    st.json(report,expanded=True)
    with st.form('answer-human-'+task['case_opaque_id']):
        target=st.text_input('Service hoặc caller -> callee theo chẩn đoán của bạn')
        kind=st.selectbox('Nhóm lỗi theo chẩn đoán của bạn',['','Resource Exhaustion','Network Delay / Packet Loss','Pod Failure','Unknown'])
        note=st.text_area('Giải thích ngắn hoặc ghi chú phiên đo')
        submit=st.form_submit_button('Chốt chẩn đoán và kết thúc ca đo')
    if submit:
        if not target.strip() or not kind:st.error('Cần tự nhập chẩn đoán trước khi chốt.');return
        ended=dt.datetime.now(dt.timezone.utc).isoformat();elapsed=timing(active['started_at'],ended,active['start_monotonic'],time.monotonic())
        session['completed_tasks'].append({**active,'ended_at':ended,**elapsed,
            'final_diagnosis':{'target':target.strip(),'fault_type':kind,'note':note},'context_id':context['incident_id']})
        session['active_task']=None;save(session_path,session)
        st.success('Đã lưu thời gian thực tế. Không hiển thị đáp án đúng/sai trước khi hoàn tất toàn bộ phiên.');st.rerun()
