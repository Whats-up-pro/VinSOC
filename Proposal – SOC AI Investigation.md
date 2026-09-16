# Proposal – SOC AI Investigation

## 1. Bài toán muốn giải quyết

Trong quá trình vận hành SOC, một **Alert không đồng nghĩa với một Incident thực sự**. Analyst trước hết cần thực hiện **Alert Triage** để thu thập context ban đầu, kiểm tra tính hợp lệ của alert và xác định liệu hoạt động được phát hiện là benign/expected hay cần tiếp tục điều tra. Việc tách Triage khỏi Investigation cũng xuất hiện trong các hệ thống security hiện đại; chẳng hạn, Google Security Operations phân tách các năng lực threat detection, alert triage, investigation và hunting, trong khi Elastic xây dựng riêng capability cho security alert triage. 

Sau khi một alert được xác định là đáng điều tra, analyst thường phải pivot qua nhiều loại dữ liệu khác nhau để trả lời các câu hỏi như: IOC có liên quan đến threat nào không, host nội bộ nào đã giao tiếp với IOC, giao tiếp đó có bất thường không, và trên host đó có process hoặc command nào liên quan hay không. Các loại evidence này đến từ những nguồn khác nhau; MITRE ATT&CK hiện chuẩn hóa chúng dưới dạng **Data Components**, chẳng hạn Network Connection Creation, Network Traffic Flow/Content, Process Creation và Command Execution. 

Vì vậy, bài toán của đề tài là xây dựng một hệ thống **AI-Assisted SOC Investigation** có khả năng hỗ trợ analyst đi từ:

**Alert → Alert Triage → Investigation → Evidence Correlation → Assessment**

Trong đó, sau bước Triage, hệ thống sử dụng một Investigation Agent để xác định **evidence nào còn thiếu** và lựa chọn skill phù hợp để thu thập evidence tiếp theo. Ba skill ban đầu gồm **CTI Investigation, Network Investigation và Endpoint Investigation**.

Điểm quan trọng là hệ thống không thực hiện một pipeline cố định kiểu `CTI → Network → Endpoint`. Agent phải dựa trên evidence hiện có để quyết định bước điều tra tiếp theo. Ví dụ, nếu CTI đã cho thấy một IP đáng ngờ nhưng chưa có bằng chứng về hoạt động nội bộ, agent có thể chuyển sang Network Investigation; nếu network evidence cho thấy một host đã kết nối tới IP đó nhưng chưa xác định được tiến trình tạo kết nối, agent tiếp tục pivot sang Endpoint Investigation.

Cách tiếp cận này phù hợp với hướng nghiên cứu gần đây về LLM hỗ trợ incident response. Tuy nhiên, nghiên cứu thực nghiệm với các security analyst cho thấy LLM vẫn có thể bỏ sót thông tin quan trọng hoặc sinh thông tin không chính xác khi được sử dụng theo hướng tự động hoàn toàn. Do đó, hệ thống được định vị là **AI-assisted**, trong đó AI hỗ trợ thu thập, tương quan và giải thích evidence nhưng kết quả phải có khả năng truy nguyên về evidence nguồn để analyst kiểm tra. 

Một yêu cầu thiết kế bổ sung là **security boundary của chính Agent**. Dữ liệu log và security event được xem là **untrusted input**, không phải instruction cho Agent. Agent chỉ được sử dụng các skill/tool được định nghĩa trước, theo hướng read-only trong phạm vi MVP; không cho phép dữ liệu từ log trực tiếp thay đổi instruction hoặc kích hoạt hành động ngoài phạm vi điều tra.

---

## 2. Outcome của bài toán giải quyết đó là gì?

Outcome chính của đề tài là một **prototype SOC Investigation Agent** có thể thực hiện investigation theo hướng evidence-driven thay vì chỉ gọi tuần tự một danh sách skill.

Luồng xử lý mục tiêu:

```text
                         ┌──────────────────┐
                         │      Alert       │
                         └────────┬─────────┘
                                  ↓
                         ┌──────────────────┐
                         │  Alert Triage    │
                         │  + Initial       │
                         │    Context       │
                         └────────┬─────────┘
                                  │
                     ┌────────────┴────────────┐
                     ↓                         ↓
              Benign / Expected        Suspicious / Needs
                     │                   Investigation
                     ↓                         │
                   Close                       ↓
                                      ┌──────────────────┐
                                      │ Investigation     │
                                      │      Agent        │
                                      └────────┬─────────┘
                                               ↓
                                    Identify Missing Evidence
                                               ↓
                              ┌────────────────────────────┐
                              │ Select Investigation Skill │
                              └─────────────┬──────────────┘
                                            ↓
                              ┌────────────────────────────┐
                              │ CTI │ Network │ Endpoint    │
                              └─────────────┬──────────────┘
                                            ↓
                                    Evidence Correlation
                                            ↓
                                  Investigation Assessment
```

**Alert Triage** là một **workflow gate**, không nhất thiết là một skill ngang hàng với CTI, Network và Endpoint. Nhiệm vụ của Triage là tạo context ban đầu và quyết định liệu alert có cần đi vào investigation sâu hơn hay có thể được đóng lại.

Sau khi đi vào Investigation, mỗi skill chịu trách nhiệm cung cấp một loại evidence cụ thể:

| Skill | Evidence chính | Có thể trả lời | Không nên tự kết luận |
|---|---|---|---|
| **CTI** | IOC reputation, threat context, malware/campaign/ATT&CK context | IOC có threat context đáng chú ý hay không | Host nội bộ có thực sự giao tiếp với IOC hay process nào sử dụng IOC |
| **Network** | Connection, source/destination, port, protocol, timestamp, frequency, fan-out... | Có hoạt động network đáng chú ý hay không | Process nào tạo connection nếu chưa có endpoint evidence |
| **Endpoint** | Process tree, parent-child, command line, user, host, execution context... | Có evidence đáng ngờ trên endpoint hay không | IOC reputation hoặc network reputation |

Kết quả cuối cùng không chỉ là một câu trả lời dạng text mà là một **Investigation Trace** gồm các evidence đã thu thập, skill đã sử dụng, reasoning/pivot giữa các bước và assessment cuối cùng. Evidence và inference được tách biệt để analyst có thể phân biệt đâu là dữ liệu quan sát được và đâu là kết luận được suy ra từ dữ liệu đó.

MVP tập trung vào **read-only investigation**. Hệ thống không thực hiện các response action như block IP, kill process, thay đổi firewall hoặc thực thi arbitrary command. Điều này giúp giới hạn blast radius trong giai đoạn prototype và tập trung đánh giá năng lực cốt lõi: **triage → evidence collection → evidence correlation → assessment**.

Về mặt triển khai, dữ liệu ban đầu có thể sử dụng mock/synthetic telemetry để kiểm soát ground truth. Tuy nhiên, schema của các loại evidence sẽ được thiết kế theo cấu trúc có khả năng ánh xạ sang các security telemetry thực tế, thay vì gắn chặt với một bộ mock data cụ thể. Điều này tạo điều kiện để thay thế data source về sau bằng SIEM, CTI hoặc endpoint telemetry thực tế.

MCP có thể được xem là **hướng integration về sau** để kết nối Agent với các security platform/API; nó không phải mục tiêu chính của MVP. Tương tự, việc đóng gói các capability thành Agent Skills có thể được thực hiện sau khi logic investigation đã ổn định. Trong 5 tuần đầu, ưu tiên là chứng minh rằng **evidence-driven orchestration thực sự hoạt động**.

---

## 3. Kế hoạch từng tuần cần làm gì?

### Tuần 1 – Xác định Investigation Workflow và Evidence Model

Phân tích workflow từ Alert Triage đến Investigation, làm rõ Triage cần thu thập context gì trước khi quyết định chuyển sang investigation.

Tiếp theo, với từng investigation question, xác định:

**Investigation Question → Required Evidence → Data Source → Skill**

Từ đó hoàn thiện boundary và input/output của ba skill CTI, Network và Endpoint; đồng thời thiết kế schema chung cho Evidence, Investigation Context và Investigation Result.

Cuối tuần cần có architecture và data flow rõ ràng, trong đó Triage là cổng vào của Investigation và Agent có khả năng lựa chọn skill dựa trên evidence còn thiếu.

### Tuần 2 – Xây dựng Triage và Investigation Skills

Triển khai Alert Triage ở mức MVP và ba skill:

- **CTI Investigation Skill**
- **Network Investigation Skill**
- **Endpoint Investigation Skill**

Ban đầu có thể sử dụng mock/synthetic telemetry nhưng output phải có cấu trúc rõ ràng và evidence phải được lưu lại để truy nguyên.

Đồng thời bổ sung security boundary cơ bản: skill chỉ thực hiện các operation được định nghĩa trước, dữ liệu từ log/event được xử lý như untrusted data và không được coi là instruction cho Agent.

### Tuần 3 – Xây dựng Investigation Agent

Xây dựng orchestrator/agent có khả năng:

1. nhận investigation context từ Triage;
2. đọc evidence hiện có;
3. xác định evidence còn thiếu;
4. lựa chọn skill phù hợp;
5. gọi skill và cập nhật Investigation Context;
6. quyết định tiếp tục pivot hay kết thúc investigation.

Mục tiêu quan trọng của tuần này là loại bỏ dependency vào pipeline cố định `CTI → Network → Endpoint`.

Ví dụ, một investigation đơn giản có thể kết thúc sau Triage hoặc CTI; một investigation phức tạp hơn có thể đi qua Network rồi Endpoint tùy thuộc vào evidence thu thập được.

### Tuần 4 – Xây dựng Scenario Benchmark và đánh giá

Xây dựng khoảng **15–20 investigation scenarios** có ground truth, bao gồm cả benign/expected activity và các trường hợp cần investigation nhiều bước.

Các scenario cần kiểm tra không chỉ kết quả cuối cùng mà cả **investigation path**: Agent có chọn đúng skill không, có thu thập evidence cần thiết không, có tránh gọi skill không cần thiết không và assessment cuối cùng có truy nguyên được về evidence hay không.

Có thể bổ sung comparison giữa:

**Fixed pipeline** `CTI → Network → Endpoint`

và

**Evidence-driven orchestration**

để kiểm tra liệu việc điều phối linh hoạt có thực sự tạo ra lợi ích thay vì chỉ làm hệ thống phức tạp hơn.

### Tuần 5 – Hoàn thiện MVP và Demo End-to-End

Hoàn thiện prototype, test các scenario, kiểm tra investigation trace và documentation.

Demo tập trung vào hai luồng đối lập:

**Benign/Expected:**

`Alert → Triage → Close`

và

**Suspicious:**

`Alert → Triage → Investigation Agent → CTI/Network/Endpoint → Evidence Correlation → Assessment`

Qua đó thể hiện rõ giá trị chính của hệ thống: **không chỉ dùng LLM để trả lời câu hỏi security, mà sử dụng Agent để điều phối quá trình thu thập và tương quan evidence nhằm hỗ trợ SOC analyst điều tra nhanh hơn và có thể kiểm chứng.**