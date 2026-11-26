"""Read-only project dashboard backed by persisted experiment evidence."""
import json
from pathlib import Path
import streamlit as st
from app.human_study import study_complete
from app.admission_progress import progress

ROOT=Path(__file__).resolve().parents[1]


def read(relative,default=None):
    path=ROOT/relative
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default


@st.fragment(run_every='15s')
def collection_progress():
    journals=sorted((ROOT/'results/dataset-collection').glob('*/journal.json'))
    if not journals:return
    journal=read(str(journals[-1].relative_to(ROOT)),{})
    completed={a['scenario_id'] for a in journal.get('attempts',[]) if a['status']=='captured_requires_review'}
    active=[a['scenario_id'] for a in journal.get('attempts',[]) if a['status']=='started']
    status=journal.get('status','unknown')
    st.progress(min(len(completed)/200,1),text=f'Đợt thu dataset mới: {len(completed)} / 200 ca — admission được theo dõi riêng')
    if status=='stopped_requires_review':
        last=journal.get('attempts',[])[-1:] or [{}]
        st.error('Đợt thu đã dừng tại '+last[0].get('scenario_id','bước kiểm tra')+': '+journal.get('error','Cần kiểm tra journal trước khi chạy tiếp.'))
        st.caption('Lượt dừng không được tính capture hoàn chỉnh. Cần xác nhận cleanup và xử lý nguyên nhân trước attempt mới.')
    else:
        st.caption('Trạng thái thu: '+status+('; đang chạy '+', '.join(active) if active else '')+'. Không tự admission hoặc gọi Gemini.')
    funnel=progress(ROOT);counts=funnel['counts']
    st.progress(min(funnel['admitted']/200,1),text=f'Admission chính thức: {funnel["admitted"]} / 200 ca — cần reviewer duyệt từng ca')
    a,b,c,d,e=st.columns(5)
    a.metric('Đã capture',funnel['captured_scenarios']);b.metric('Chờ review',counts['pending_review']+counts['approved_record_incomplete'])
    c.metric('Duyệt, chờ apply',counts['approved_ready_to_apply']);d.metric('Bị từ chối',counts['rejected_requires_new_attempt'])
    e.metric('Admitted',funnel['admitted'])
    if counts['rejected_requires_new_attempt']:
        st.warning('Ca bị từ chối không được tính; cần attempt mới cùng setting theo protocol trước khi đạt đủ 200.')
    st.caption('Tiến độ tự cập nhật mỗi 15 giây khi trang đang mở. Áp dụng phiếu đã duyệt bằng `make admission-apply` khi controller dừng.')
    st.button('Cập nhật tiến độ thu',key='refresh_collection_progress')


def overview():
    registry=read('experiments/candidate-registry.json',{'attempts':[],'official_admitted':0})
    attempts=registry['attempts'];captured=sum(x['execution_status']=='captured_requires_review' for x in attempts)
    reports=list((ROOT/'results/diagnoses').glob('*/B*/result.json'))
    cols=st.columns(4)
    for col,label,value in zip(cols,['Capture local','Report Gemini','Biến thể','Admission'],
                               [captured,len(reports),'5 / 5',f'{registry["official_admitted"]} / 200']):
        col.metric(label,value)
    st.caption('Số lượt capture gồm các lần chạy lặp; chưa phải số ca chính thức. Mở giao diện không gọi Gemini.')
    collection_progress()
    left,right=st.columns([1.4,1])
    with left:
        st.subheader('Luồng xử lý sự cố')
        st.markdown('**Telemetry → Alert → Context → Chẩn đoán → Kỹ sư review**')
        st.write('Thu log, metric và trace từ Sock Shop; chuẩn hóa bằng chứng và đối chiếu runbook để hỗ trợ điều tra.')
        st.info('Bắt đầu ở **Incident** để mở dữ liệu collector, hoặc **Phân tích** để xem telemetry và chạy B0 local. Các kết quả Gemini trước đó nằm trong **Báo cáo**.')
        st.subheader('Kiểm chứng mới nhất')
        validation=read('results/detector-validation/network-v041-20261123.json') or read('results/detector-validation/live-validation.json',{})
        rows=[]
        for case in validation.get('cases',[]):
            trigger=case['trigger'];labels=trigger['trigger']['labels']
            rows.append({'Scenario':case['scenario_id'],'Route':labels.get('route'),
                'Collector':trigger['status'],'Alert tới collector (s)':round(trigger['injection_confirmed_to_received_seconds'],2)})
        if rows:st.dataframe(rows,hide_index=True,width='stretch')
    with right:
        st.subheader('Trạng thái triển khai')
        st.dataframe([{'Hạng mục':name,'Trạng thái':status} for name,status in [
            ('Thu telemetry và cảnh báo','Đã chạy thật'),('CPU / RAM / mạng / Pod','Đã calibration'),
            ('B0 local và B1–B3 Gemini','Đã có triển khai'),('Dataset 200 ca','Chưa admission'),
            ('Protocol / independent review','Cần hoàn tất'),('Human baseline / ROI','Chưa đo')]],hide_index=True,width='stretch')
        st.caption('Đây là trạng thái theo hồ sơ đã lưu. Tab Incident lấy dữ liệu collector hiện tại.')
    verification=read('results/environment/product-verification.json',{})
    if verification:
        st.subheader('Kiểm chứng hạ tầng và dữ liệu mới')
        a,b,c=st.columns(3)
        a.metric('Frontend tracing', '4 peer đã xác minh')
        b.metric('Collector',verification.get('collector',{}).get('version','—'))
        c.metric('Kiểm thử Python',verification.get('python_tests',{}).get('passed',0))
        soak_meta=verification.get('post_rollout_soak',{})
        soak=read(soak_meta.get('result',''),{}) if soak_meta.get('result') else {}
        if soak.get('status')=='passed_short_soak':
            st.success('Soak sau rollout đạt 600 giây; chỉ là xác nhận ổn định ngắn hạn.')
        elif soak.get('status'):
            st.warning('Soak sau rollout cần kiểm tra: '+soak['status'])
        else:
            st.info('Soak sau rollout đang chạy; chưa kết luận đạt.')
        st.caption('Context 0.4.1/prompt 0.2 đã chạy hai ca mạng development; grounding review và benchmark chính thức còn chờ. Report cũ giữ nguyên phiên bản ban đầu.')
    st.subheader('Các cấu hình so sánh')
    st.dataframe([{'Cấu hình':mode,'Đầu vào':data,'Xử lý':process} for mode,data,process in [
        ('B0','Metric quan sát','Rule local, có thể abstain'),('B1','Log','Gemini'),
        ('B2','Log + runbook','Gemini và RAG'),('B3','Log + metric + trace + runbook','Gemini và RAG')]],hide_index=True,width='stretch')
    comparison=read('results/evaluation/network-v041-b0-b3-development.json') or read('results/evaluation/multifault-b0-b3-development.json')
    if comparison:
        st.subheader('So sánh development mới nhất')
        st.dataframe([{'Cấu hình':r['mode'],'Đúng Top-1':f'{r["top1_correct"]["count"]} / {r["denominator"]}',
                       'Report hợp lệ':r['valid_reports']} for r in comparison['summaries'] if r['fault_class']=='all'],hide_index=True,width='stretch')
        if comparison.get('context_version')=='0.4.1':
            st.caption('Hai ca mạng reference, context 0.4.1/prompt 0.2. B3 đúng Top-1 cả hai; còn giả thuyết bổ sung cần review. Chưa phải test accuracy hoặc bằng chứng cải thiện chỉ do prompt.')
        else:
            st.caption('Bốn ca reference, chưa phải test accuracy. Hai ca mạng của B3 chưa đúng directed edge; không loại kết quả sai khỏi mẫu số.')


def dataset():
    audit=read('results/evaluation/dataset-validation.json',{})
    st.subheader('Dataset và chất lượng thực nghiệm')
    st.warning('200 manifest đã qua dry-run không đồng nghĩa đã chạy thực tế và admission đủ 200 ca.')
    a,b,c=st.columns(3);a.metric('Scenario trong plan',audit.get('plan_audit',{}).get('case_count',0));b.metric('Lượt capture',audit.get('captured_cases',0));c.metric('Official admitted',f'{audit.get("official_admitted",0)} / 200')
    st.progress(min(audit.get('official_admitted',0)/200,1),text='Tiến độ admission chính thức')
    if audit.get('errors'):st.error('Audit có lỗi: '+str(audit['errors']))
    else:st.success('Audit local gần nhất đạt. Independent review và protocol freeze còn pending.')
    if audit.get('cases'):
        visible_cases=[r for r in audit['cases'] if r['split']!='test' or study_complete(ROOT)]
        st.dataframe([{'Scenario':r['scenario_id'],'Biến thể':r['variant'],'Split':r['split'],
            'Execution':r['execution_status'],'Admission':r['admission_status'],
            'Review độc lập':r.get('independent_human_review','Chưa capture')} for r in visible_cases],hide_index=True,width='stretch')
    st.caption('Các ca cùng scenario là lượt lặp, không phải cấu hình lỗi độc nhất. Chưa có test accuracy chính thức.')
    validation=read('results/detector-validation/completion-checks.json',{})
    st.subheader('Kết quả kiểm thử đã lưu')
    st.dataframe([{'Kiểm tra':k,'Đạt':v} for k,v in validation.get('checks',{}).items()],hide_index=True,width='stretch')
    if audit:st.download_button('Tải hồ sơ audit dataset',json.dumps(audit,ensure_ascii=False,indent=2),'dataset-validation.json','application/json')
    baseline=read('results/evaluation/b0-development.json')
    if baseline:
        with st.expander('B0 development — chưa phải benchmark chính thức'):
            st.dataframe(baseline['summaries'],hide_index=True,width='stretch')
            st.write('B0 abstain ở network khi chỉ có latency, không tự suy ra edge. Mẫu gồm các ca chạy lặp và observation sau recovery.')
    for path in ('docs/progress/STATUS.md','docs/progress/DATASET-VALIDATION.md','docs/progress/NETWORK-DETECTOR-VALIDATION.md'):
        file=ROOT/path
        if file.exists():
            with st.expander(file.stem):st.markdown(file.read_text())
