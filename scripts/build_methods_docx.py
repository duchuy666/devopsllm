#!/usr/bin/env python3
"""Build the methods appendix with the bundled document Python runtime."""
from pathlib import Path
from docx import Document
from docx.shared import Cm,Pt,RGBColor,Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/submission/phu_luc_phuong_phap_va_tai_lap.docx'


def table(doc,headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.autofit=False
    for cell,width in zip(t.columns,widths):cell.width=Cm(width)
    for i,text in enumerate(headers):t.rows[0].cells[i].text=text
    for row in rows:
        cells=t.add_row().cells
        for cell,text in zip(cells,row):cell.text=str(text)
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        item=OxmlElement('w:'+edge)
        for key,value in [('val','single'),('sz','4'),('color','D9D9D9')]:item.set(qn('w:'+key),value)
        borders.append(item)
    t._tbl.tblPr.append(borders)
    for ri,row in enumerate(t.rows):
        props=row._tr.get_or_add_trPr();props.append(OxmlElement('w:cantSplit'))
        if ri==0:props.append(OxmlElement('w:tblHeader'))
        for ci,cell in enumerate(row.cells):
            cell.width=Cm(widths[ci]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc=cell._tc.get_or_add_tcPr();margins=OxmlElement('w:tcMar')
            for edge in ('top','left','bottom','right'):
                item=OxmlElement('w:'+edge);item.set(qn('w:w'),'80');item.set(qn('w:type'),'dxa');margins.append(item)
            tc.append(margins)
            if ri==0:
                fill=OxmlElement('w:shd');fill.set(qn('w:fill'),'DCEAF7');tc.append(fill)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(2);p.paragraph_format.line_spacing=1.05
                for r in p.runs:r.font.size=Pt(11);r.font.bold=ri==0;r.font.color.rgb=RGBColor(0,0,0)
    doc.add_paragraph().paragraph_format.space_after=Pt(1)


def main():
    d=Document();s=d.sections[0];s.page_width=Inches(8.5);s.page_height=Inches(11)
    s.top_margin=Cm(2.2);s.bottom_margin=Cm(2);s.left_margin=Cm(2.5);s.right_margin=Cm(2)
    s.footer_distance=Cm(.9)
    for name,size in [('Normal',12),('Title',20),('Subtitle',12),('Heading 1',15),('Heading 2',13)]:
        style=d.styles[name];style.font.name='Times New Roman';style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
        fonts=style.element.get_or_add_rPr().find(qn('w:rFonts'))
        for key in list(fonts.attrib):
            if key.endswith('Theme'):fonts.attrib.pop(key)
        for key in ('ascii','hAnsi','eastAsia','cs'):fonts.set(qn('w:'+key),'Times New Roman')
        style.paragraph_format.line_spacing=1.12;style.paragraph_format.space_after=Pt(5)
        if name.startswith('Heading'):style.paragraph_format.keep_with_next=True;style.paragraph_format.space_before=Pt(10)
    d.styles['Title'].paragraph_format.space_after=Pt(8)
    for style in d.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    footer=s.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    run=footer.add_run('Phụ lục phương pháp  |  ');run.font.size=Pt(10)
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    p=d.add_paragraph('Phụ lục phương pháp thực nghiệm',style='Title')
    d.add_paragraph('Hệ thống hỗ trợ chẩn đoán sự cố DevOps với Gemini và RAG',style='Subtitle')
    d.add_paragraph('Phụ lục mô tả protocol thu dữ liệu, đối chiếu B0–B3, review và tái lập trên Sock Shop. Các số lượng dưới đây là thiết kế nghiên cứu; số ca admitted và kết quả benchmark phải được đối chiếu riêng với registry và báo cáo chấm đã hoàn tất.')
    d.add_heading('1 Môi trường và thiết kế dataset',level=1)
    d.add_paragraph('Testbed chạy trên MacBook Air M2 có 16 GB RAM. Docker được cấp 8 GiB; Minikube dùng 7 GiB và bốn CPU. Payment, catalogue và user dùng bản Go ARM64 đã ghim source; một số image legacy còn chạy qua giả lập AMD64. Vì vậy kết quả không đại diện trực tiếp cho hiệu năng production hoặc máy khác kiến trúc.')
    table(d,['Nhóm lỗi','Số ca kế hoạch','Biến thể'],[
        ['Resource Exhaustion',67,'CPU và memory stress'],['Network Delay / Packet Loss',67,'Delay và packet loss trên directed edge'],['Pod Failure',66,'Pod kill dưới các điều kiện traffic khác nhau']], [6.4,3.1,7.4])
    d.add_paragraph('Plan 0.3 giữ 200 cấu hình danh nghĩa thuộc 28 họ kịch bản. Chữ ký cấu hình gồm variant, target, parameters, duration và traffic pause; đổi ID, seed hoặc tên profile không tạo cấu hình mới. Các ca cùng họ vẫn có thể tương quan và gần nhau về triệu chứng. Split giữ nguyên 120 reference, 40 validation và 40 test theo họ fault–variant–target, không chia random từng lượt.')
    d.add_paragraph('Bản 0.2 có 48 lượt Pod lặp setting. Trước khi mở validation/test, các lượt Pod chưa chạy được đổi traffic pause; bảy ca reference đã hoàn tất giữ nguyên từng hàng scenario. Release cũ, raw và provenance được bảo toàn. Migration ghi rõ các file thay đổi; observation, provider, prompt và mã inference không đổi khi chuyển tiếp bảy ca này.')
    d.add_paragraph('Release prospective v3 ghim 50 file và giữ mười ca reference nguyên provenance trước khi mở heldout. Collector được sửa OOM bằng cách thu một job tại một thời điểm, ghi JSON theo luồng và tăng giới hạn RAM từ 192 lên 512 MiB; thay đổi dịch vụ hỗ trợ được ghi riêng. Mỗi batch tối đa bốn ca, Pod failure cuối batch. Giữ máy thức và không deploy trong lúc thực nghiệm.')
    d.add_page_break()
    d.add_heading('2 Cửa sổ quan sát và chất lượng dữ liệu',level=1)
    table(d,['Mục đích','Mốc thời gian','Cửa sổ và cách dùng'],[
        ['Collector vận hành','Alert được nhận','120 giây trước và 30 giây sau alert; lưu thời điểm context sẵn sàng.'],
        ['Benchmark offline','Controller xác nhận inject','30 giây trước và 30 giây sau; chỉ giữ span kết thúc trước cutoff.'],
        ['Review tác động','Warmup đến recovery','Raw toàn lượt để đối chiếu tác động, cleanup và ảnh hưởng ngoài target.']], [3.8,4.4,8.7])
    d.add_paragraph('Mốc inject chỉ xác định cửa sổ offline. Loại lỗi, target được gán, chaos parameters, qdisc và quyết định review không đi vào context gửi model. Raw toàn lượt và observation được lưu riêng; không dùng dữ liệu sau cutoff để chẩn đoán benchmark, không diễn giải latency replay thành live Time to Diagnosis.')
    d.add_heading('Trình tự của một ca',level=2)
    for text in [
        'Kiểm Node và Pod Ready, không còn chaos, working set và PSI trong gate. Receipt soak 600 giây phải đạt UTC gate, còn mới trong 15 phút và khớp manifest, Pod UID cùng restart counter.',
        'Warmup 30 giây phải có checkout và không có request lỗi. Resolve lại service IP và giới hạn tài nguyên trước inject; kiểm server dry-run.',
        'Inject có ownership label; chờ AllInjected, ghi timestamp và cgroup trong fault. Clock bất thường, node-local OOM tăng hoặc memory stall sẽ dừng ca để review.',
        'Cleanup đúng resource sở hữu, quan sát recovery, xuất metric/log/trace. Giữ cả request lỗi trong fault; không tự coi chúng là lý do loại ca có tác động thật.',
        'Tạo observation cố định từ raw; kiểm đủ modality và source hash. Structural check không tự xác nhận effect hoặc admission. Reviewer kiểm tác động đúng target, recovery, relevance và near duplicate.']:
        d.add_paragraph(text,style='List Number')
    d.add_paragraph('Log và trace export có giới hạn hữu hạn; khi chạm cap phải chia cửa sổ hoặc ghi incomplete. Query trace tối đa 500 trace mỗi query, tối đa 32 query; dedup theo service, trace ID và span ID để giữ shared RPC ở hai service. Có source không đồng nghĩa đủ coverage hoặc đúng relevance.')
    d.add_paragraph('Bản ghi admitted cần quyết định review thực tế, reviewer/pseudonym, thời gian có timezone, lý do, vị trí raw và provenance khớp. Failed attempt được giữ riêng, không tính vào 200 ca chính thức. Hai attempt cùng scenario không được dùng để lấp một scenario còn thiếu.')
    d.add_page_break()
    d.add_heading('3 Cấu hình trợ lý và nguyên tắc chấm',level=1)
    table(d,['Mã','Đầu vào quan sát','Xử lý'],[
        ['B0','Metric cùng observation','Rule local, có thể abstain'],['B1','Log template','Gemini không retrieval'],
        ['B2','Log template và tri thức truy xuất','Gemini với RAG'],['B3','Log, metric, trace và tri thức truy xuất','Gemini với RAG đa nguồn']], [1.2,8.3,7.4])
    d.add_paragraph('Provider được đổi sang Gemini theo lựa chọn triển khai. Model yêu cầu là gemini-3.8-flash, thinking level low; embedding là gemini-embedding-001, 768 chiều. Mỗi report tối đa 4.096 output token. Model version thực trả về, prompt fingerprint, usage, lỗi và latency được lưu cho từng lần gọi; request không tự retry.')
    d.add_paragraph('Context 0.4.1 giới hạn mặc định 24.000 ký tự, giữ metric usage/limit của các Pod có biến động và các client edge quan sát. Peer chỉ thuộc allowlist dịch vụ; attributes có thể chứa payload được bỏ. Mỗi evidence ID liên kết về query, label, timestamp hoặc service/trace/span trong raw. ID context phụ thuộc nội dung và cấu hình đã xử lý, không phụ thuộc tên thư mục fault.')
    d.add_paragraph('KB hiện là năm runbook tĩnh được ghim nội dung; B2/B3 lấy tối đa ba runbook. Test không được index vào Qdrant. Thiết kế này đánh giá retrieval từ runbook, chưa phải operational memory học từ toàn bộ case reference. Review nội dung được lưu riêng, gắn với hash; không tự đổi KB hoặc reindex giữa các điều kiện.')
    d.add_heading('Độ đúng và bằng chứng',level=2)
    d.add_paragraph('Top 1 và Top 3 chỉ tính đúng khi cùng service hoặc cùng directed edge và cùng nhóm lỗi với ground truth. Đảo hướng edge hoặc chỉ đúng một đầu không được tính đúng. Mẫu số gồm các case admitted đã khai báo; report thiếu, lỗi API hoặc schema lỗi không bị âm thầm bỏ. Báo riêng coverage và Wilson 95 phần trăm; tương quan trong cùng họ là một giới hạn của khoảng tin cậy theo case.')
    d.add_paragraph('Kiểm tự động chỉ xác nhận schema, context ID và evidence ID tồn tại. Grounding cần chấm từng claim và đối chiếu raw, tách supported, partially supported, unsupported, contradicted và unverifiable. Một giả thuyết Top 1 đúng không chứng minh các giả thuyết bổ sung đúng. Nếu chỉ có một reviewer độc lập thì công bố giới hạn đó, không dựng số liệu đồng thuận hai người.')
    d.add_page_break()
    d.add_heading('4 Review con người và tái lập',level=1)
    d.add_paragraph('Nhãn runbook liên quan do người review điền để tính Recall và MRR; cosine score không thay thế relevance label. Confidence do model tự khai báo chưa được calibration, không được diễn giải như xác suất đúng đã kiểm chứng.')
    d.add_paragraph('Phiên pilot được đăng ký trước với một người tham gia và 14 nhiệm vụ test: bảy cặp cùng họ kịch bản, mỗi cặp dùng hai ca khác nhau, một ca B0/dashboard và một ca có B3 hỗ trợ. Thứ tự được xáo trộn với seed cố định. Đây không phải crossover cùng case; khác biệt điều kiện không đủ chứng minh quan hệ nhân quả hoặc đại diện cho quần thể kỹ sư.')
    d.add_paragraph('Người tham gia tự nhập pseudonym và xác nhận chưa xem đáp án. Bộ đếm bắt đầu khi người đó mở ca và kết thúc khi tự chốt diagnosis. UI không tự nhập quyết định, không phản hồi đúng/sai giữa các nhiệm vụ; test ground truth và report ngoài điều kiện được giữ ẩn đến khi kết thúc phiên. UTC và monotonic được đối chiếu; phiên có clock bất thường không được điền số giây thay thế.')
    d.add_paragraph('Thời gian người được đo trên observation đã tải và report trợ lý đã có. API/retrieval latency replay và live alert đến report là các đại lượng khác, phải báo riêng. Giá trị giờ công chỉ được tính khi có số đo thực tế; đơn giá kỹ sư và tỷ giá nếu dùng phải công bố là giả định hoặc nguồn có ngày. Không suy ra ROI thực tế chỉ từ tốc độ sinh report. Chi phí token tham chiếu khác hóa đơn; embedding và index phải được tính hoặc ghi rõ chưa gồm.')
    d.add_heading('Hồ sơ cần đi kèm kết quả',level=2)
    d.add_paragraph('Mỗi ca giữ scenario, ground truth, traffic, raw, observation, recipe/source hash, quality review và quyết định admission. Bảng kết quả phải ghi đúng số ca thu/admitted ở từng split, từng fault class; giữ failure cases, detector miss, API failure, thiếu modality và các thay đổi môi trường.')
    d.add_paragraph('Bộ source không chứa .env, API key, kubeconfig hoặc database backup có tài khoản. Replay dùng telemetry đã lưu và không đòi hỏi gọi API mới. Live demo cần cluster, tunnel và ngân sách phù hợp. Hệ thống chỉ đề xuất khắc phục để người vận hành xác nhận, không tự sửa production.')
    d.add_heading('Vị trí kiểm chứng trong dự án',level=2)
    for text in [
        'config/collection-protocol.yaml và experiments/scenario-plan.json: cửa sổ, plan 0.3 và split.',
        'results/collection-releases/20261124-prospective-v3: release, source archive và migration.',
        'docs/runbooks/RB-15-prospective-collection.md: chạy, theo dõi, review và admission.',
        'experiments/human-study-plan.json: đăng ký phiên đo; chỉ người điều phối đọc mapping trước phiên.',
        'results/evaluation và results/api-calls: scorer, usage và lỗi; không thay bằng kết quả dự kiến.']:
        d.add_paragraph(text,style='List Bullet')
    for paragraph in d.paragraphs:
        for border in list(paragraph._p.iter(qn('w:pBdr'))):border.getparent().remove(border)
    d.core_properties.title='Phụ lục phương pháp thực nghiệm';d.core_properties.author='';d.core_properties.subject='Protocol và tái lập Sock Shop Gemini RAG'
    OUT.parent.mkdir(parents=True,exist_ok=True);d.save(OUT);print(OUT)


if __name__=='__main__':main()
