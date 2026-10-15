"""Offline report authoring. Run from repo root with ReportLab and DejaVu Serif fonts.
Reads saved artifacts only; no SDK/API/SQL execution.
"""
from pathlib import Path
import json,gzip,html,re
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Preformatted,KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY,TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing,Rect,String,Line,Polygon

ROOT=Path.cwd(); OUT=ROOT/'docs/evaluation'; NAME='VinSOC_Official_Experiments_Report_2026-10-15'
R1=json.loads((ROOT/'results/evaluation_v1/r1/generalization_v1_20261015/report.json').read_text())
BASE=ROOT/'results/evaluation_v1/text2sql_integration_v1'
P=json.loads((BASE/'pipeline_protocol3_20261015/audit_summary.json').read_text())
E=json.loads((BASE/'evaluation_protocol3_20261015/audit_summary.json').read_text())
CASE=json.loads((BASE/'pipeline_protocol3_20261015/live/E0_ctu_cross_09368110b7091cb8.json').read_text())
for name,file in [('VN','DejaVuSerif.ttf'),('VN-Bold','DejaVuSerif-Bold.ttf')]:pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/dejavu/'+file))
navy=colors.HexColor('#173c58');gray=colors.HexColor('#eff3f6');amber=colors.HexColor('#fff2d8')
styles={
 'body':ParagraphStyle('body',fontName='VN',fontSize=13,leading=17,spaceAfter=8,alignment=TA_JUSTIFY),
 'title':ParagraphStyle('title',fontName='VN-Bold',fontSize=22,leading=29,textColor=navy,spaceAfter=18),
 'h':ParagraphStyle('h',fontName='VN-Bold',fontSize=16,leading=22,textColor=navy,spaceAfter=12),
 'small':ParagraphStyle('small',fontName='VN',fontSize=10.5,leading=14,spaceAfter=7),
 'cell':ParagraphStyle('cell',fontName='VN',fontSize=11.2,leading=14),
 'code':ParagraphStyle('code',fontName='VN',fontSize=10.2,leading=14,spaceAfter=10),
}
story=[];md=[]
def nice(text):
    terms='thành|hash|gồm|và|có|dùng|hạn|trong|cả|thắng|thua|hòa|mẫu|tốn|phí|thứ|trả|nhất|cho|từ|chỉ|là|tổng|lũy|toàn|trên|đủ|tất|giữ|nguồn|đều|scenario|Python|full|required|CI|Dev|protocol|matched|Re-parse|Partial|missing|value|số|bằng|Wilson|Calibration|External|Tổng'
    text=re.sub(r'(?<![\w])('+terms+r')(?=[0-9])',r'\1 ',text)
    text=re.sub(r';(?=\S)','; ',text)
    text=re.sub(r'(?<=[A-Za-zÀ-ỹ]),(?=[A-Za-zÀ-ỹ0-9])',', ',text)
    text=re.sub(r'(?<=[0-9])USD',' USD',text)
    text=re.sub(r'=(?=[0-9])','= ',text)
    text=text.replace('là-54','là -54').replace('khoảng[-','khoảng [-')
    for a,b in [('records','bản ghi'),('responses','phản hồi'),('authored/reviewed','được biên soạn và duyệt'),('factual verification','kiểm chứng dữ kiện'),('human review','người thật duyệt')]:
        text=re.sub(r'\b'+re.escape(a)+r'\b',b,text)
    return text

def p(text,kind='body'):
 text=nice(text)
 md.append(text+'\n');story.append(Paragraph(html.escape(text).replace('\n','<br/>'),styles[kind]))
def heading(text):md.append('## '+text+'\n');story.append(Paragraph(html.escape(text),styles['h']))
def table(rows,widths=None):
 rows=[[nice(str(x)) for x in row] for row in rows]
 md.append('\n'.join('| '+' | '.join(str(x) for x in row)+' |' for row in [rows[0],['---']*len(rows[0]),*rows[1:]])+'\n')
 t=Table([[Paragraph(html.escape(str(x)),styles['cell']) for x in row] for row in rows],colWidths=widths or [440/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),gray),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,navy),('LINEBELOW',(0,1),(-1,-1),.25,colors.lightgrey),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,10)])
def page():story.append(PageBreak());md.append('\n---\n')
def code(text):md.append('```sql\n'+text+'\n```\n');story.append(Paragraph(html.escape(text).replace('\n','<br/>'),styles['code']))
def diagram():
 d=Drawing(440,210);xs=[0,153,306];ys=[158,88,18];w=134;h=43
 labels=[['Câu hỏi gốc','QueryProvider\nnative routing','Orchestrator\nnetwork_query'],['Typed result\nvà evidence','SqlExecutor\nworker cách ly','TextToSQLService\nE0 đã khóa'],['Assessment\nmô hình thật','Kiểm chứng EX,\nprovenance, facts','Người thật\nduyệt riêng']]
 for iy,y in enumerate(ys):
  for ix,x in enumerate(xs):
   d.add(Rect(x,y,w,h,fillColor=gray,strokeColor=navy,strokeWidth=.7,rx=4,ry=4));lines=labels[iy][ix].split('\n')
   for j,line in enumerate(lines):d.add(String(x+w/2,y+h/2+(len(lines)-1)*6-j*12,line,textAnchor='middle',fontName='VN',fontSize=9.2,fillColor=navy))
 def arrow(x1,y1,x2,y2):
  d.add(Line(x1,y1,x2,y2,strokeColor=navy));dx=x2-x1;dy=y2-y1
  if abs(dx)>abs(dy):sgn=1 if dx>0 else -1;pts=[x2,y2,x2-5*sgn,y2+3,x2-5*sgn,y2-3]
  else:sgn=1 if dy>0 else -1;pts=[x2,y2,x2+3,y2-5*sgn,x2-3,y2-5*sgn]
  d.add(Polygon(pts,fillColor=navy,strokeColor=navy))
 arrow(134,180,153,180);arrow(287,180,306,180);arrow(373,158,373,131);arrow(306,109,287,109);arrow(153,109,134,109);arrow(67,88,67,61);arrow(134,39,153,39);arrow(287,39,306,39)
 story.append(d);md.append('Luồng query: câu hỏi gốc → native routing → network_query → TextToSQLService(E0) → worker SQL cách ly → typed result/evidence → assessment → kiểm chứng → người duyệt.\n')

md.append('# VinSOC - Báo cáo thực nghiệm chính thức ngày 15/10/2026\n')
story.append(Paragraph('VinSOC<br/>Kết quả thực nghiệm và giới hạn hiện tại',styles['title']))
p('Bản cập nhật ngày 15/10/2026 cho mentor và báo cáo cuối khóa. Nguồn là các lượt API thật đã lưu; mọi chỗ thiếu vẫn được giữ để người xem đánh giá đúng mức độ hoàn thiện.',kind='small')
heading('1. Hệ thống đã chứng minh được điều gì?')
p('VinSOC đã có bằng chứng thật cho quyết định chọn tool của R1 và phép đo Text-to-SQL rộng hơn bộ tám câu ban đầu. R1 bổ sung đạt 119/120. Với R2, E0 đạt 69/96 và E3 đạt 17/96; E0 đã được chọn từ calibration trước khi chạy evaluation.')
p('Luồng tích hợp cũng đã chạy thật từ câu hỏi qua tool call, SQL, DB và assessment. Tuy nhiên, lượt 32 câu dừng ở case thứ 17 do kết quả vượt giới hạn payload. Vì vậy có thể phân tích năng lực và lỗi của hệ thống, nhưng chưa được tuyên bố nghiệm thu đầy đủ pipeline hoặc bộ bốn demo đã khóa.')
table([['Phạm vi','Bằng chứng hiện có','Trạng thái'],['Calibration','48/48 records thật','Đã khóa E0'],['Evaluation R2','192/192 records thật','Đã đối soát và CI'],['R1 bổ sung','120/120 responses;119 đúng','Đã đối soát và CI'],['Pipeline CTU32','16 hoàn tất;1 partial;15 thiếu','Chưa hoàn tất'],['SOC trace chính thức','0/128; preflight không gọi API','Thiếu review nguồn/gates']],widths=[104,220,116])
p('Không có mô hình nào được gọi lại để sửa một kết quả xấu. Khôi phục DB, gold SQL, prompt, scorer và hai ZIP đã pin được bảo toàn. Human review không được tự điền hoặc tự phê duyệt.',kind='small')
page()
heading('2. Kiến trúc chung và vị trí từng môđun')
p('Hệ thống có hai kiểu đầu vào: cảnh báo/IOC cho điều tra SOC và câu hỏi ngôn ngữ tự nhiên cho nhánh query. Orchestrator điều phối công cụ, EvidenceStore giữ bằng chứng và liên kết nguồn, assessment tổng hợp diễn giải, còn kiểm chứng và người duyệt là hai bước riêng.')
diagram()
p('Sơ đồ mô tả nhánh query đã thực thi trong lượt này. SQL của mô hình chỉ chạy trong worker tách biệt, DB chỉ đọc, có giới hạn mạng, bộ nhớ, CPU và thời gian. Bằng chứng cách ly đến từ các quan sát độc lập ở required CI jobs, không lấy field isolation do executor tự khai làm chứng minh.')
p('R1 đo quyết định chọn ba tool SOC: cti_enrichment, network_investigation và endpoint_investigation. Benchmark R1 trả native calls nhưng không chạy công cụ sản xuất. Trong pipeline query, routing vào network_query được đo riêng; không dùng điểm R1 để suy ra điểm routing của pipeline.')
p('R2 dùng cùng TextToSQLService và SqlExecutor ở benchmark và public investigate_query. Điều này nối phép đo SQL với luồng thật. Chia sẻ runtime không có nghĩa toàn bộ pipeline tự động đạt: routing, khả năng chuyển result sang assessment, factual verification và human review đều có thể thất bại độc lập.')
page()
heading('3. R1: mạnh ở hợp đồng tool, còn rủi ro đối số')
p('Từ câu yêu cầu gốc và schema công cụ, mô hình trả native tool calls. Runner chuẩn hóa đối số và đối chiếu với matcher/scorer đã khóa. Bộ bổ sung có 24 no-tool, 54 single-tool, 30 two-tool và 12 three-tool; bộ dev lịch sử vẫn được giữ riêng.')
table([['Chỉ số','Kết quả','Ý nghĩa'],['Trajectory success','119/120 =99,17%','Đúng cả tool và đối số'],['Wilson95%','95,43%-99,85%','Giả định độc lập'],['No-tool','24/24','Biết không gọi tool'],['Required/critical coverage','154/155','Mẫu số gồm mọi expected args'],['Native requests/responses','120/120','Không retry; đủ ID/usage']],widths=[160,127,153])
p('Case gen_096 cho thấy giới hạn thực tế: mô hình chọn đúng CTI và endpoint nhưng thêm hai ký tự e, làm IOC hash dài từ64 thành66 ký tự. Khi điều tra bảo mật, sai chuỗi định danh có thể dẫn tới truy vấn nhầm đối tượng. Tool-name F1 cao vì vậy không thay được kiểm tra đối số và nguồn IOC.')
p('Scorer gốc đánh dấu case này không đạt. Trường thống kê cũ critical_arg_errors vẫn bằng0 và error_summary rỗng do runner không gán lại field đó; audit đối chiếu từng match ghi rõ một critical mismatch (hash64→66 ký tự), giữ nguyên artifacts và không sửa điểm lịch sử.')
p('Độ chính xác cao áp dụng cho bộ authored/reviewed có các họ tình huống liên quan, chưa phải mẫu ngẫu nhiên đại diện toàn bộ SOC. Bộ dev lịch sử đạt 22/24, nhưng có 11 đáp án được điều chỉnh sau khi xem đầu ra. Không gộp hai bộ thành một mẫu144 hoặc gọi đây là independent holdout.')
p('Lượt mới tốn0,04673480USD;88.185 input,7.163 output,0 cached token. Latency SDK p50 ≈ 0,959s và p95 ≈ 1,714s, không bao gồm toàn bộ gate/CI.',kind='small')
page()
heading('4. R2: đối chứng 96 câu cho thấy E0 phù hợp hơn')
p('Calibration gồm24 câu cho mỗi điều kiện; evaluation gồm64 câu trên tám database ngoài SOC và32 câu CTU. Tổng cộng có192 records evaluation thật, chấm trên DB gốc bằng worker. Bộ evaluation dùng9 database;13 là tổng DB đã khôi phục cho cả calibration và evaluation.')
table([['Tập đo','E0','E3'],['Calibration24','15/24 =62,50%','4/24 =16,67%'],['External64','46/64 =71,875%','10/64 =15,625%'],['CTU32','23/32 =71,875%','7/32 =21,875%'],['Tổng96','69/96 =71,875%','17/96 =17,708%'],['Calls / chi phí evaluation','96 /0,07442350USD','482 /0,62127495USD']],widths=[130,155,155])
p('E0 sinh SQL trực tiếp từ schema. E3 thêm liên kết lược đồ và nhiều bước tool-assisted trước SQL. Dưới cùng hợp đồng giới hạn1.000 output token và tối đa sáu call/case cho E3, chuỗi dài hơn tạo thêm điểm gãy thay vì cải thiện kết quả.')
p('E3 có52 INVALID_LINKED_SCHEMA,21 MODEL_PARSE_ERROR;17 trong21 lỗi parse kết thúc vì chạm giới hạn output. Không quy cả52 lỗi schema cho token cap. Phần lớn E3 không có final SQL, nên vấn đề chính xuất hiện trước bước thực thi DB.')
p('Đối chứng theo cặp: E3 thắng2, thua54, hòa40 so với E0. Chênh lệch E3-E0 là-54,17 điểm phần trăm; bootstrap theo database cho khoảng[-65,28;-43,75]. Kết quả ủng hộ lựa chọn E0 trong phạm vi bộ này, không chứng minh E0 vượt trội trên mọi miền.')
p('EX so kết quả trên một snapshot; semantic test-suite accuracy chưa được đo. Các giá trị mặc định false/0 trong report gốc không phải một phép đo semantic mới. Các bảng trung bình theo database, miền dữ liệu, độ khó và đặc trưng SQL nằm trong JSON đầy đủ.',kind='small')
page()
heading('5. Pipeline: phân biệt SQL đúng và E2E đạt')
p('Lượt chính thức gọi public investigate_query với câu hỏi nguyên gốc, E0 đã khóa và hash mã nguồn và dữ liệu khớp calibration. Có 50 phản hồi: 17 routing, 17 SQL và 16 assessment. Chi phí0,03810390USD, không unknown cost hay pending exposure.')
table([['Chỉ số trên mẫu số32','Đã xác nhận','Cách đọc'],['Integrated EX','12 đúng;16 đã chấm','Chưa tính tỷ lệ đủ 32'],['Routing / runtime','16 trace /17 dùng runtime','Partial không có trace trọn vẹn'],['Provenance / facts','16 /5','Facts dựa trên16 assessment'],['Technical workflow','3','Cần human review'],['Người duyệt chấp thuận','0','Không tự phê duyệt']],widths=[173,130,137])
p('Case UDP thứ17 trả9.780 dòng, không bị cắt bớt dòng. Riêng result cần ít nhất177.205 byte, vượt giới hạn32.768 byte ở bước chuyển bằng chứng sang assessment. Ngoại lệ thoát khỏi case làm dừng suite. Receipt gốc chỉ giữ ValueError; kết luận payload dựa trên đối chiếu result thật với đúng nhánh code đã chạy.')
p('Re-parse16 assessment với đúng evidence lưu lại cho5 OK,9 UNKNOWN_OR_DUPLICATE_QUERY_OBSERVATION và2 MISSING_QUERY_OBSERVATION. Các bảng nhiều dòng cần định vị row/cell; chỉ tên cột lặp lại không đủ để verifier xác nhận một giá trị cụ thể.')
table([['Demo cố định','Trạng thái'],['COUNT -708b66575657429a','missing'],['UDP -66b8e92a76c3359b','incomplete'],['NULL -3f659571f998adb0','technical_failed'],['AVG -bce6d3679ade4cd6','missing']],widths=[270,170])
p('Giữ nguyên cả bốn ID, không thay bằng case thành công. Tất cả tỷ lệ chính thức của pipeline còn null, mẫu số32. Ba case đạt kỹ thuật ngoài bộ bốn chỉ phục vụ phân tích và review, không đóng gate demo.',kind='small')
page()
heading('6. Một trace thật để giải thích cơ chế')
p('Ví dụ bổ sung: ctu_cross_09368110b7091cb8. Đây là trace đã lưu, không thay thế bốn demo ID. Câu hỏi yêu cầu đếm các cặp source/destination IP khác nhau của UDP ở CTU scenario5, giữ ngữ nghĩa tuple DISTINCT với NULL của DuckDB.')
p('Câu hỏi gốc: '+CASE['generation']['question'],kind='small')
p('Native routing truyền đúng câu hỏi vào network_query. SQL sau được TextToSQLService E0 sinh từ API.')
code(CASE['generation']['final_sql'])
table([['Typed result','Giá trị thật'],['Cột / kiểu','distinct_udp_src_dst_pairs /BIGINT'],['Số dòng / giá trị','1 /38.695'],['SQL EX / provenance /facts','Đạt các checks kỹ thuật đã lưu']],widths=[180,260])
p('Trích nguyên văn assessment của mô hình: '+CASE['metadata']['query_policy']['assessment']['assessment'],kind='small')
p('Observation trỏ vào ev_8746607d_3, field distinct_udp_src_dst_pairs, value38695. Result hash và execution lineage gắn SQL với snapshot. Validator kiểm lại dữ kiện có trong evidence; scorer đối chiếu kết quả SQL. Hai kiểm tra này không xác nhận toàn bộ ngữ nghĩa của lời diễn giải hoặc mức rủi ro bảo mật.')
p('Trace hiện awaiting_human. Mô hình cũng nêu giới hạn snapshot tĩnh, phạm vi scenario5/UDP và chưa kiểm chứng CTI/endpoint. Người trình bày nên mở native response, typed result và verification cạnh nhau; không nói một số đếm lưu lượng chứng minh có hoặc không có tấn công.')
p('Viewer giữ toàn bộ chuỗi bằng chứng và raw response trước parse. Phần chưa chạy vẫn hiện thiếu; việc xem lại không gọi API.',kind='small')
page()
heading('7. Kết luận và thứ tự cải tiến')
p('Ưu điểm rõ nhất là khả năng truy nguồn và kiểm tra lại: selection xuất phát từ48 calibration records, evaluation có192 records, R1 có120 native responses, và pipeline giữ cả checkpoint gây lỗi. DB thật và worker cách ly giúp phân biệt lỗi mô hình với lỗi thực thi; mô hình không được tự tạo evidence hoặc tự duyệt kết luận.')
p('Giới hạn lớn nhất nằm ở hợp đồng tích hợp: bước chuyển result chưa có bản chiếu rút gọn và verifier chưa diễn đạt tốt bảng nhiều dòng hoặc kết quả rỗng. E0 có SQL đúng trong12 case đã chấm của pipeline nhưng chỉ3 case đạt toàn bộ kỹ thuật. Một chỉ số SQL riêng lẻ không đại diện chất lượng báo cáo cuối.')
table([['Ưu tiên','Thay đổi cần thiết','Cách chứng minh'],['1','Giới hạn phần kết quả vào prompt; giữ result đầy đủ và hash','Result UDP9780 dòng;không tăng cap ngầm'],['2','Dẫn chứng theo dòng/ô và kết quả rỗng','Re-parse16 native assessment,giữ lỗi cũ'],['3','Lỗi từng case và resume có ledger,chống gửi trùng','Partial1+missing15;không reset window'],['4','Sửa telemetry lỗi R1 trong phiên bản sau','gen_096:matcher≠legacy error field'],['5','Đánh giá độc lập và review nguồn SOC','Không gọi bộ authored là holdout']],widths=[55,221,164])
p('Các thay đổi có ý nghĩa với prompt/runtime phải là protocol phiên bản mới, được khóa trước phép đo mới; không vá ngược source đã chấm hoặc chạy lại lịch sử để cứu điểm. Thực nghiệm SOC128 còn chờ đủ 12 review nguồn (hiện 0/12) và bộ gate riêng. Tập kiểm tra độc lập và đối chứng matched8 cũ vẫn để sau.')
p('Bốn lượt được trình bày (calibration protocol3, evaluation, R1 mới, pipeline partial) có892 responses, tổng0,95400045USD. Riêng query canonical ledger tích lũy1,33381910USD; R1 mới là0,04673480USD riêng. Đây là đối soát usage đã lưu, không phải tuyên bố số dư tài khoản hay toàn bộ hóa đơn lịch sử.',kind='small')
page()
heading('8. Bằng chứng và cách mở khi báo cáo')
p('Nên chiếu kết quả trước, sau đó giải thích kiến trúc và trace. Nếu mở viewer, nói rõ đang xem lại lượt API thật đã lưu. Tình trạng pipeline partial và bốn demo ID cần được nói ngay từ đầu để người nghe không nhầm một trace minh họa với nghiệm thu đầy đủ.')
p('Trên Windows, từ thư mục repo, giải nén bundle rồi mở index.html. Việc xem không cần API key, không chạy DB và không phát sinh phí. JSON trong ZIP giữ nguyên byte Linux để có thể đối soát hash và ký review đúng receipt.',kind='small')
code('Expand-Archive .\\results\\evaluation_v1\\text2sql_integration_v1\\pipeline_protocol3_20261015\\offline_demo_bundle.zip -DestinationPath .\\vinsoc_offline_demo\nStart-Process .\\vinsoc_offline_demo\\index.html')
refs=[('Calibration','38532017308','2f8234a3db086fb634b91dc2e5ba50d1a77db4fe /CI38684701741'),('Evaluation','38687383299','ff37425719b3009d33d166ae3faa19ccc35a09e8 /CI38698148403'),('R1 bổ sung','38699129318','aea0b9b2197db69ba45727142b2fd5c5c3dbd58f /CI38701290199'),('Pipeline partial','38699219559','producer ff374257; CI38698148403; không COMPLETE')]
for title,run,sha in refs:
 p(title+': https://github.com/Whats-up-pro/VinSOC/actions/runs/'+run,kind='small');p(sha,kind='small')
p('Gói dữ liệu có receipt, manifest SHA-256 và verify.py ở từng thư mục kết quả. Auditor đọc artifacts, tính lại thống kê/usage và không gọi mô hình hoặc SQL. Bản report gốc giữ nguyên; kiểm chứng bổ sung nằm trong audit_summary và diagnostic.',kind='small')
p('CI của producer và các commit công bố evaluation/R1 đều đạt trên Python3.11/3.12: full1465 passed,7 skipped mỗi phiên bản; required140 guards và13 real-data checks mỗi phiên bản đều0 skip. Các skip full suite không được dùng làm bằng chứng cho job bắt buộc. CI của gói bàn giao cuối cần đối chiếu đúng SHA trên GitHub Actions.',kind='small')
p('Kết luận hiện tại: R1 và R2 đã có phép đo rộng hơn và bằng chứng có thể kiểm lại. Pipeline đã chứng minh có luồng thực thi thật, đồng thời bộc lộ lỗi tích hợp cụ thể; chưa đủ điều kiện tuyên bố hoàn tất32 case, bốn demo hoặc release cuối.',kind='small')

def footer(c,doc):
 c.setStrokeColor(colors.lightgrey);c.line(25*mm,20*mm,190*mm,20*mm);c.setFont('VN',8);c.setFillColor(navy);c.drawString(25*mm,15*mm,'VinSOC | Thực nghiệm thật - 15/10/2026');c.drawRightString(190*mm,15*mm,str(doc.page))
path=OUT/(NAME+'.pdf');doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=25*mm,rightMargin=20*mm,topMargin=23*mm,bottomMargin=25*mm,title='VinSOC - Kết quả thực nghiệm chính thức',author='VinSOC project',allowSplitting=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
(OUT/(NAME+'.md')).write_text('\n'.join(md),encoding='utf-8')
print(path)
