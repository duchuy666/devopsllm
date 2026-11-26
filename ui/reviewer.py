"""Human-only review forms. Saving a form never grants official admission."""
import datetime as dt
import json
from pathlib import Path
import uuid
import streamlit as st
from scripts.apply_admission_review import validate_review,propose
from scripts.review_network_case import summarize
from app.human_study import test_review_unlocked

ROOT=Path(__file__).resolve().parents[1]


def render_review():
    st.subheader('Review độc lập dữ liệu thực nghiệm')
    st.caption('Dành cho người review: có ground truth để kiểm tác động. Không gửi dữ liệu từ tab này tới Gemini hoặc KB. Lưu phiếu không tự admission.')
    cases=[]
    unlock_test=test_review_unlocked(ROOT)
    for path in sorted((ROOT/'data/candidates').glob('CANDIDATE-*')):
        if (path/'review-packet.json').exists():
            ground=json.loads((path/'ground-truth.json').read_text())
            if ground['scenario']['split']=='test' and not unlock_test:continue
            cases.append(path)
    if not unlock_test:st.info('Ground truth test được giữ ẩn đến khi hoàn tất phiên đo chẩn đoán. Reference và validation vẫn có thể review.')
    if not cases:
        st.info('Chưa có ca prospective hoàn tất để review.');return
    selected=st.selectbox('Ca cần review',cases,format_func=lambda path:path.name,key='review_candidate')
    original=json.loads((selected/'review-packet.json').read_text())
    ground=json.loads((selected/'ground-truth.json').read_text());scenario=ground['scenario']
    output=ROOT/'results/review-handoff/prospective-review'/(selected.name+'.json')
    packet=json.loads(output.read_text()) if output.exists() else original
    record=packet['independent_review'];quality=original['structural_review']
    st.write({'scenario':scenario['scenario_id'],'split':scenario['split'],'variant':scenario['variant'],
              'target':scenario['target'],'admission':ground['admission_status']})
    st.dataframe([{'Kiểm tra':key,'Đạt':value} for key,value in quality['checks'].items()],hide_index=True,width='stretch')
    rows=[]
    for item in quality['observations']['target_metric_phases']:
        metric=item['metric'];scale=1024**2 if metric in ('memory','memory_limit') else 1
        row={'Metric':metric,'Pod':item['pod'],'Đơn vị':'MiB' if scale!=1 else 'core' if metric in ('cpu','cpu_limit') else 'value'}
        for phase,values in item['phases'].items():
            row[phase+' mean']=round(values['mean']/scale,4) if values.get('mean') is not None else None
            row[phase+' max']=round(values['max']/scale,4) if values.get('max') is not None else None
        rows.append(row)
    if rows:st.dataframe(rows,hide_index=True,width='stretch')
    st.write({'target_pod_uid_changed':quality['observations']['target_pod_uid_changed'],
              'checkout':quality['observations']['traffic_completed_journeys'],
              'failed_requests':quality['observations']['traffic_failed_requests'],
              'observation_quality':ground.get('observation_capture',{}).get('quality')})
    if scenario['variant'].startswith('network-'):
        try:
            observation=summarize(selected)
            st.write({'qdisc_reported_drops':observation['qdisc_max_reported_drops']})
            st.dataframe([{'Nguồn':name,'Giai đoạn':phase,**values}
                for name in ('route_latency_ms','matching_client_span_latency_ms')
                for phase,values in observation[name].items()],hide_index=True,width='stretch')
        except (OSError,KeyError,ValueError) as exc:st.warning('Cần đối chiếu raw network evidence: '+type(exc).__name__)
    evidence=[name for name in ('ground-truth.json','chaos-status.json','network-counters.json',
              'warmup-state.json','recovery-state.json','traffic.json','provenance.json',
              'telemetry/metrics.json','telemetry/logs.json','telemetry/traces.json',
              'observation/telemetry/capture.json') if (selected/name).is_file()]
    if st.checkbox('Mở raw evidence',key='raw-'+selected.name):
        name=st.selectbox('File bằng chứng',evidence,key='raw-file-'+selected.name)
        st.json(json.loads((selected/name).read_text()),expanded=False)
    if ground['admission_status']=='admitted':
        st.success('Ca đã admission; phiếu review được giữ để audit.');return
    suffix=selected.name
    with st.form('independent-review-'+suffix):
        reviewer=st.text_input('Mã hoặc pseudonym của người review',value=record.get('reviewer_id') or '')
        decisions=['pending','approved','rejected']
        decision=st.selectbox('Quyết định',decisions,index=decisions.index(record.get('decision','pending')),
            format_func=lambda value:{'pending':'Chưa chốt','approved':'Đồng ý đưa vào dataset','rejected':'Không đồng ý — cần xử lý'}[value])
        flags={}
        for key,label in [('target_effect_confirmed','Đã xác minh tác động đúng target'),
                          ('recovery_confirmed','Đã xác minh cleanup và recovery'),
                          ('telemetry_relevant','Đã đối chiếu telemetry phù hợp và đủ'),
                          ('near_duplicate_review','Đã kiểm split, trùng lặp và khai báo replication')]:
            flags[key]=st.checkbox(label,value=record.get(key) is True)
        prior=[loc.get('file') if isinstance(loc,dict) else loc for loc in record.get('evidence_locations',[])]
        locations=st.multiselect('Các file đã đối chiếu',evidence,default=[name for name in prior if name in evidence])
        books=[p.stem for p in sorted((ROOT/'knowledge/runbooks').glob('*.md'))]
        relevant=st.multiselect('Runbook có liên quan — nhãn độc lập cho đánh giá retrieval',books,
            default=[name for name in record.get('relevant_runbook_ids',[]) if name in books])
        relevance_reviewed=st.checkbox('Tôi đã chấm relevance của runbook; danh sách rỗng nghĩa là không có runbook liên quan',value=record.get('runbook_relevance_reviewed') is True)
        reason=st.text_area('Lý do và vị trí chi tiết trong raw evidence',value=record.get('reason') or '')
        submit=st.form_submit_button('Lưu phiếu review local')
    if submit:
        if decision!='pending' and (not reviewer.strip() or not reason.strip() or not locations):
            st.error('Cần mã reviewer, lý do và ít nhất một file bằng chứng.');return
        updated={'reviewer_id':reviewer.strip() or None,'reviewed_at':dt.datetime.now(dt.timezone.utc).isoformat() if decision!='pending' else None,
                 'decision':decision,**flags,'reason':reason.strip() or None,
                 'relevant_runbook_ids':relevant,
                 'runbook_relevance_reviewed':relevance_reviewed,
                 'evidence_locations':[{'file':name} for name in locations]}
        candidate_packet={**packet,'independent_review':updated}
        if decision=='approved':
            try:
                validate_review(updated);propose(selected,candidate_packet,ROOT)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                st.error('Phiếu chưa đủ điều kiện: '+str(exc));return
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists():
            history=output.parent/'history';history.mkdir(exist_ok=True)
            (history/(selected.name+'-'+uuid.uuid4().hex+'.json')).write_bytes(output.read_bytes())
        temporary=output.with_suffix('.json.tmp');temporary.write_text(json.dumps(candidate_packet,ensure_ascii=False,indent=2)+'\n');temporary.replace(output)
        st.success('Đã lưu phiếu local. Official admission chưa thay đổi; cần áp dụng quyết định ở checkpoint khi registry không còn bị controller giữ.')
    st.caption('Người review tự xác nhận các check sau khi đọc bằng chứng; giao diện không xác thực danh tính hoặc tính độc lập của người điền.')


def render_book_review(book):
    import hashlib
    path=ROOT/'results/review-handoff/runbook-review.json'
    if not path.exists():return
    document=json.loads(path.read_text());matches=[r for r in document['runbooks'] if r['file']==book.name]
    if len(matches)!=1:st.warning('Chưa có phiếu review tương ứng.');return
    record=matches[0];digest=hashlib.sha256(book.read_bytes()).hexdigest()
    st.caption('Review nội dung runbook; phiếu nằm ngoài KB, không gọi embedding hoặc reindex.')
    if record['source_sha256']!=digest:
        st.error('Nội dung đã đổi so với phiếu; cần kiểm lại release và lập phiếu đúng phiên bản.');return
    st.write('Trạng thái review: '+record['decision'])
    with st.form('book-review-'+book.stem):
        reviewer=st.text_input('Mã reviewer',value=record.get('independent_reviewer') or '')
        choices=['pending','approved','rejected']
        decision=st.selectbox('Kết luận review runbook',choices,index=choices.index(record['decision']),
            format_func=lambda value:{'pending':'Chưa chốt','approved':'Nội dung phù hợp','rejected':'Cần sửa trước khi sử dụng'}[value])
        reason=st.text_area('Nhận xét và căn cứ kiểm chứng',value=record.get('reason') or '')
        submit=st.form_submit_button('Lưu review runbook local')
    if submit:
        if decision!='pending' and (not reviewer.strip() or not reason.strip()):
            st.error('Cần mã reviewer và căn cứ cho quyết định.');return
        latest=json.loads(path.read_text());target=next(r for r in latest['runbooks'] if r['file']==book.name)
        history=path.parent/'runbook-review-history';history.mkdir(exist_ok=True)
        (history/(book.stem+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(target,ensure_ascii=False,indent=2)+'\n')
        target.update(decision=decision,independent_reviewer=reviewer.strip() or None,
                      independent_reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat() if decision!='pending' else None,
                      reason=reason.strip() or None)
        latest['status']='independent_review_complete' if all(r['decision']=='approved' for r in latest['runbooks']) else 'review_in_progress'
        temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)
        st.success('Đã lưu quyết định; nội dung và index KB giữ nguyên.')
