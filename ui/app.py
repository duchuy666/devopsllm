import json
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from app.context_builder import build_context
from app.gemini_provider import settings
from app.diagnosis import diagnose
from app.live_context import prepare_live
from app.baseline import diagnose_rules
from ui.dashboard import overview,dataset
from ui.reviewer import render_review,render_book_review
from ui.human_study import render_study
from app.human_study import hidden_test_contexts

ROOT=Path(__file__).resolve().parents[1]
st.set_page_config(page_title='SHYN Incident Assistant',layout='wide')
st.markdown('''<style>
.stApp {background:#f5f7fb;color:#17243b}
.block-container {max-width:1450px;padding-top:2rem}
div[data-testid="stMetric"] {background:white;border:1px solid #e1e7f0;border-radius:14px;padding:18px}
div[data-testid="stMetricLabel"] {color:#52627b}
button[data-baseweb="tab"] {font-weight:600}
.shyn-header {background:linear-gradient(110deg,#102943,#165a73);padding:28px 32px;border-radius:18px;color:white;margin-bottom:24px}
.shyn-header h1 {color:white;font-size:30px;padding:4px 0 10px}
.shyn-header p {color:#cbe0ed;margin:0}
</style><div class="shyn-header"><p>SHYN · INCIDENT WORKSPACE</p>
<h1>Trợ lý chẩn đoán sự cố DevOps</h1>
<p>Quan sát hệ thống, điều tra bằng chứng và theo dõi chất lượng thực nghiệm.</p></div>''',unsafe_allow_html=True)

home,live,replay,saved,knowledge,quality,reviewer,human=st.tabs(['Tổng quan','Incident','Phân tích','Báo cáo','Runbook','Dataset & kiểm thử','Review dữ liệu','Thời gian chẩn đoán'])
with home:overview()
with quality:dataset()
with reviewer:render_review()
with human:render_study()
with live:
    st.write('Các alert được Alertmanager chuyển đến collector. Trạng thái captured nghĩa là đã lưu telemetry, chưa phải đã có chẩn đoán LLM.')
    if st.button('Cập nhật incident'):
        st.session_state.pop('live_incidents',None)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/incidents',timeout=5) as response:
            rows=json.load(response)
        if rows:
            label={'captured':'Đầy đủ log, metric, trace','partial':'Đủ log và metric; trace bị cắt theo giới hạn xuất'}
            st.dataframe([{'Incident':r['id'],'Nhận lúc (UTC)':r['received_at'][:19].replace('T',' '),
                           'Telemetry':label.get(r['status'],r['status'])} for r in rows],width='stretch',hide_index=True)
            st.caption('Collector chỉ xuất tối đa một số trace mỗi cửa sổ để giới hạn dung lượng; khi chạm giới hạn, incident ghi "partial" '
                       'nhưng vẫn đủ dữ liệu để dựng context và chẩn đoán.')
            available=[r['id'] for r in rows if r['status'] in ('captured','partial')]
            if available:
                live_id=st.selectbox('Incident cần mở',available)
                if st.button('Chuẩn hóa incident này trên máy'):
                    try:
                        with st.spinner('Đang lấy telemetry và chuẩn hóa context…'):
                            live_context,_,directory=prepare_live(live_id)
                        st.success('Đã chuẩn hóa '+live_context['incident_id']+'. Chưa gọi Gemini.')
                        st.json({'missing_sources':live_context['missing_sources'],
                                 'counts':{k:len(live_context[k]) for k in ('metrics','logs','traces')}})
                    except Exception as exc:
                        st.error('Không chuẩn hóa được incident: '+type(exc).__name__)
        else: st.info('Chưa có incident trong collector.')
    except Exception:
        st.info('Collector chưa truy cập được. Chạy make collector-forward tại thư mục dự án.')

with replay:
    st.write('Chọn telemetry đã lưu để xem bằng chứng và chạy lại một cấu hình chẩn đoán. Kết quả replay được lưu riêng với thời gian xử lý live.')
    candidates=[]
    for case in sorted((ROOT/'data/candidates').glob('CANDIDATE-*')):
        ground=case/'ground-truth.json'
        if ground.exists() and json.loads(ground.read_text()).get('dataset_role')=='prospective_candidate':
            # Precommitted cohorts are evaluated through the benchmark tooling,
            # not exposed to ad-hoc replay or prompt tuning in this tab.
            continue
        if (case/'telemetry/metrics.json').exists():candidates.append(case/'telemetry')
    for case in sorted((ROOT/'data/live').glob('INC-*')):
        if (case/'telemetry/metrics.json').exists():candidates.append(case/'telemetry')
    for case in sorted((ROOT/'data/pilot').glob('PILOT-*')):
        if (case/'telemetry-corrected/metrics.json').exists(): candidates.append(case/'telemetry-corrected')
        elif (case/'telemetry-complete/metrics.json').exists(): candidates.append(case/'telemetry-complete')
        elif (case/'telemetry/metrics.json').exists(): candidates.append(case/'telemetry')
    if not candidates:
        st.info('Chưa có telemetry được xuất.')
    else:
        selected=st.selectbox('Bộ dữ liệu đã lưu',list(range(len(candidates))),format_func=lambda i:f'Observation {i+1:02d}')
        directory=candidates[selected]
        st.caption('Dữ liệu phát triển/live cần review trước khi đưa vào dataset chính thức. Nhãn lỗi không được dùng trong context.')
        context,evidence=build_context(directory)
        st.code(context['incident_id'],language=None)
        a,b,c=st.columns(3)
        a.metric('Bằng chứng metric',len(context['metrics']))
        b.metric('Log template',len(context['logs']))
        c.metric('Span được chọn',len(context['traces']))
        if context['missing_sources']: st.warning('Nguồn dữ liệu thiếu: '+', '.join(context['missing_sources']))
        with st.expander('Metric',expanded=True):
            st.dataframe(context['metrics'],width='stretch',hide_index=True)
        with st.expander('Log template'):
            st.dataframe([{'evidence_id':r['evidence_id'],'service':r['service'],'count':r['count'],'template':r['template']}
                          for r in context['logs']],width='stretch',hide_index=True)
        with st.expander('Trace và span'):
            st.dataframe(context['traces'],width='stretch',hide_index=True)
        st.download_button('Tải context JSON',json.dumps(context,ensure_ascii=False,indent=2),
                           file_name=context['incident_id']+'.json',mime='application/json')
        st.download_button('Tải chỉ mục bằng chứng',json.dumps(evidence,ensure_ascii=False,indent=2),
                           file_name=context['incident_id']+'-evidence.json',mime='application/json')
        with st.expander('B0 · Phân tích bằng rule local'):
            st.caption('Không gọi API. B0 dùng cùng context quan sát; latency cao chưa đủ kết luận lỗi mạng hoặc directed edge.')
            if st.button('Chạy B0 trên dữ liệu này'):
                st.session_state['baseline_result']={'context_id':context['incident_id'],'report':diagnose_rules(context)}
            baseline=st.session_state.get('baseline_result',{})
            if baseline.get('context_id')==context['incident_id']:
                st.json(baseline['report'])
        config=settings()
        mode=st.selectbox('Cấu hình', ['B1','B2','B3'],format_func=lambda m:{
            'B1':'B1 · Log, không retrieval','B2':'B2 · Log và RAG','B3':'B3 · Log, metric, trace và RAG'}[m])
        has_index=(ROOT/'.runtime/knowledge-index.json').exists()
        if not config['key']:
            st.info('Cần đặt GEMINI_API_KEY trong file .env trên máy. Chưa gửi dữ liệu đến Gemini.')
        elif mode!='B1' and not has_index:
            st.info('Knowledge base chưa được index. Chạy make rag-index sau khi kiểm tra kết nối Gemini.')
        st.caption(f'Model cấu hình: {config["model"]}. Mỗi lần phân tích gọi tối đa một lần sinh báo cáo; RAG cần thêm embedding cho truy vấn.')
        st.caption('Nút chẩn đoán gửi context đang xem và runbook liên quan tới Google Gemini API.')
        if st.button('Chẩn đoán bằng Gemini',disabled=not config['key'] or (mode!='B1' and not has_index)):
            try:
                with st.spinner('Đang phân tích bằng chứng…'):
                    result=diagnose(context,mode,ROOT/'results/diagnoses')
                st.session_state['diagnosis_result']=result
            except Exception as exc:
                st.error(f'Không tạo được báo cáo: {type(exc).__name__}. Kiểm tra cấu hình, quota và kết nối; chưa có kết quả chẩn đoán hợp lệ.')
        result=st.session_state.get('diagnosis_result')
        archived=ROOT/'results/diagnoses'/context['incident_id']/mode/'result.json'
        if (not result or result.get('context_id')!=context['incident_id'] or result.get('mode')!=mode) and archived.exists():
            result=json.loads(archived.read_text())
        if result and result['context_id']==context['incident_id'] and result['mode']==mode:
            report=result['generated']['report']
            st.write('Trạng thái: '+report['status'])
            st.dataframe(report['hypotheses'],width='stretch',hide_index=True)
            for action in report['recommended_actions']: st.write('• '+action)
            st.caption('Confidence là ước lượng chưa hiệu chỉnh. Evidence ID tồn tại chưa chứng minh bằng chứng hỗ trợ đúng kết luận; cần kỹ sư review.')
            with st.expander('Model, usage và latency'): st.json({k:v for k,v in result['generated'].items() if k!='report'})

with saved:
    reports=sorted((ROOT/'results/diagnoses').glob('*/B*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    hidden=hidden_test_contexts(ROOT)
    reports=[p for p in reports if p.parent.parent.name not in hidden]
    st.caption('Xem các lần phân tích đã chạy. Mở mục này không gọi Gemini thêm lần nào.')
    if not reports:
        st.info('Chưa có report đã lưu.')
    else:
        chosen=st.selectbox('Report',reports,format_func=lambda p:p.parent.parent.name+' · '+p.parent.name)
        record=json.loads(chosen.read_text())
        generated=record['generated']; report=generated['report']
        st.write('Trạng thái: '+report['status'])
        for position,hypothesis in enumerate(report['hypotheses'],1):
            st.subheader(f'{position}. {hypothesis["service"]} · {hypothesis["fault_type"]}')
            st.write(hypothesis['root_cause'])
            st.write(hypothesis['rationale'])
            st.caption('Evidence: '+', '.join(hypothesis['evidence_ids']))
        st.write('Hành động đề xuất')
        for action in report['recommended_actions']:st.write('• '+action)
        st.caption('Đây là các giả thuyết cần kỹ sư xác nhận. Một pilot đúng không chứng minh accuracy tổng thể.')
        st.json({k:v for k,v in generated.items() if k!='report'})
        if generated.get('estimated_paid_api_cost_usd') is not None:
            st.caption('Chi phí là tham chiếu paid tier, chưa đối chiếu hóa đơn và chưa gồm embedding/index.')
        st.download_button('Tải report JSON',json.dumps(record,ensure_ascii=False,indent=2),
                           file_name=report['incident_id']+'-report.json',mime='application/json')

with knowledge:
    books=sorted((ROOT/'knowledge/runbooks').glob('*.md'))
    st.write(f'{len(books)} runbook tri thức. Review độc lập được lưu riêng và gắn với hash nội dung; không tự thay đổi KB hoặc reindex.')
    for book in books:
        with st.expander(book.stem):
            st.markdown(book.read_text().split('---',2)[-1])
            render_book_review(book)
