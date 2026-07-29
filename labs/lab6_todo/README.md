# Lab 6 — TodoWrite: วางแผน Multi-step Task

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 2.2

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 3 (Skills) + เริ่มแตะ Layer 2 (Memory) — TodoWrite คือ state ของแผนงานหลายขั้นที่ไหลข้าม step

---

## จุดประสงค์การเรียนรู้

- เพิ่ม internal tools (`todo_write`, `todo_update`) เพื่อให้ agent วางแผนงานหลายขั้นก่อนเริ่มลงมือ
- เข้าใจการจัดการ **state ใน agent** ด้วย class `TodoState` ที่เก็บ todo list ไว้ใน memory
- เห็นว่า agent ใช้ todo เป็นแผนงาน แล้วอัปเดตสถานะ (todo → doing → done) ระหว่างทำงานจริงด้วย MCP tools
- เพิ่ม Context State แบบ Pure Python เพื่อสังเกต loop โดยไม่เปลี่ยนการตัดสินใจของ Agent

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab6_todo/agent_todo.py
```

(default task คือรายงาน HR 3 ขั้น: นับพนักงานแยกแผนก → top-3 มูลค่าโครงการ → สรุปเชิงธุรกิจ)

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab6_todo/agent_todo.py`

### `TodoState` — state ของ todo list (in-memory)

```python
class TodoState:
    def write(self, items: list[str]) -> str: ...    # สร้าง todo ใหม่ทั้งหมด
    def update(self, index: int, status: str) -> str: ...  # เปลี่ยนสถานะทีละข้อ
    def render(self) -> str: ...                     # แสดง [ ] / [~] / [x] ต่อ item
```

`render()` คืน string เช่น `"[x] 1. นับพนักงาน\n[~] 2. top-3\n[ ] 3. สรุป"` — LLM อ่านและรู้สถานะปัจจุบันของแผนงาน

> จุดที่ควรเปิดอ่าน: method `update()` — มี logic รองรับทั้ง 1-based index (ตาม render) และ 0-based (ที่ LLM บางครั้งส่งมาผิด) เพื่อความทนทาน

### `build_tools(registry)` — รวม todo tools + MCP tools

```python
todo_tools = [
    {tool: "todo_write", ...},   # สร้าง todo list
    {tool: "todo_update", ...},  # อัปเดตสถานะ
]
return todo_tools + registry.openai_tools   # รวมกับ MCP tools
```

agent เห็น tools ทั้งหมดรวมกัน — ตัดสินใจว่าจะใช้ todo tool หรือ MCP tool ตามความเหมาะสม

### `run(question, registry, max_steps=30)` — agent loop + todo dispatch

```python
if name == "todo_write":
    result = todo.write(args.get("items", []))
elif name == "todo_update":
    result = todo.update(args.get("index"), args.get("status"))
else:
    result = registry.dispatch(name, args)   # MCP tool
```

todo tools ถูก handle ใน Python โดยตรง (ไม่ผ่าน MCP) ส่วน tools อื่นส่งไป `registry.dispatch()`

### System prompt — บังคับ planning ก่อน action

```python
SYSTEM = (
    "...ถ้างานมี 3 ขั้นขึ้นไป ให้เรียก todo_write เขียนแผนก่อนเริ่มลงมือ "
    "แล้วทำทีละข้อ เรียก todo_update เปลี่ยนสถานะเป็น 'doing' ก่อนทำ และ 'done' เมื่อเสร็จ..."
)
```

pattern นี้คือ **plan-then-execute** ที่ให้ agent โปร่งใสและตรวจสอบได้

## Context State Phase 1

ไฟล์ `context_state.py` เพิ่ม control state ขนาดเล็กโดยไม่ใช้ LangGraph, LLM,
embedding, relevance scoring หรือ rolling summary:

```text
ContextState
├─ original_goal          # immutable anchor
├─ phase / active_step
├─ completed_steps
├─ accepted_evidence_refs # เก็บ reference ไม่ยัดผล tool ซ้ำ
├─ recent action+result signatures
├─ recent error signatures
└─ steps/tool/error budgets
```

ตรวจ drift แบบ deterministic 3 กรณี:

1. tool + arguments + result เดิมซ้ำ
2. exception type + message เดิมซ้ำ
3. action kind ไม่ตรงกับ phase ปัจจุบัน

การตรวจใช้ SHA-256 จาก canonical JSON จึงไม่ถือว่า tool ชื่อเดียวกันแต่ arguments
หรือผลต่างกันเป็น loop และไม่ใช้ keyword/embedding ที่อาจไม่แม่นกับภาษาไทย

Phase นี้เป็น **observe-only**: เมื่อพบ drift จะแสดง `[CONTEXT ALERT]` แต่ไม่ block
tool, ไม่ replan และไม่เปลี่ยนคำตอบ เพื่อรักษาพฤติกรรมของ original agent ไว้เป็น baseline

ทดสอบโดยไม่เรียก OpenRouter หรือ MCP:

```bash
python -m unittest -v tests.test_lab6_context_state
```

สิ่งที่ยังไม่ทำใน Phase 1: persistence, cold storage จริง, context compaction,
rolling summary, semantic drift และ recovery policy

ผล live baseline 10 คำถามแสดงว่า Phase 1 ยังไม่เพิ่ม semantic accuracy:

- [Ground-truth contract](../../artifacts/lab6_context_baseline_ground_truth.md)
- [Experiment report](../../artifacts/lab6_context_baseline_report.md)
- `artifacts/lab6_context_baseline_runs.json` เก็บ raw outputs และ metrics

## Evidence State + Final Semantic Observer (Phase 2)

Phase 2 แยก state เป็นสองส่วน:

```text
ControlState                    EvidenceState
├─ goal / phase / steps         ├─ evidence id
├─ action/error signatures      ├─ tool + arguments
└─ budgets                      ├─ raw result + stable hash
                                └─ bounded evidence pack
```

เมื่อ Agent เสนอคำตอบ Final Observer จะตรวจ question + accepted evidence +
proposed answer แล้วคืน structured verdict:

```text
approve | rewrite | query_more | refuse_decision
```

`rewrite` และ `refuse_decision` ถูกตรวจซ้ำอีกหนึ่งรอบก่อนแสดงผล หากยังไม่ผ่าน
ระบบจะ fail closed แทนการปล่อยคำตอบที่ตรวจไม่ผ่าน ส่วน MCP มี hard budget 12 calls
ต่อ task เพื่อไม่ให้ query วนโดยไม่มีขอบเขต

รัน Phase 2 (default):

```bash
python labs/lab6_todo/agent_todo.py \
  "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก"
```

รัน baseline โดยปิด Final Observer:

```bash
python labs/lab6_todo/agent_todo.py --semantic-observer off \
  "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก"
```

ผลทดลองสด 20 runs:

- [Phase 2 experiment report](../../artifacts/lab6_semantic_phase2_report.md)
- `artifacts/lab6_semantic_phase2_runs.json` เก็บ raw outputs และ metrics

Phase 2 เพิ่ม strict grounded answer จาก 0/10 เป็น 4/10 ใน sample นี้ แต่มี latency
เพิ่มและยังมี failure ด้าน data grain จึงเป็น experimental branch ไม่ใช่
production-ready implementation

## Claim Ledger + Dynamic Observation (Phase 2B)

Phase 2B เพิ่มส่วนกลางหลัง MCP call:

```text
Tool Result
   ↓
EvidenceFact(subject, predicate, value, unit, grain, evidence_id)
   ↓
ClaimLedger(required → proved | contradicted)
   ↓
DynamicObservation
  accept | query_more | replan | stop
```

Claim Planner สร้าง evidence requirements จากคำถามก่อนเริ่มทำงาน และตรวจว่า
coverage/rate ใช้ numerator กับ denominator grain เดียวกัน หากมีเพียง record count
แต่ต้องการ entity coverage จะขอ `COUNT(DISTINCT entity_id)` เพิ่ม

Dynamic Observer มี timeout 45 วินาทีและ budget สูงสุด 6 LLM observations ต่อ task
เพื่อป้องกัน latency แบบไร้ขอบเขต หาก reviewer ล้มเหลว raw evidence ยังคงถูกเก็บและ
Agent ทำงานต่อได้ ส่วน Final Observer จะได้รับทั้ง Claim Ledger, structured facts และ
raw evidence

ปิดเฉพาะ Phase 2B เพื่อเปรียบเทียบกับ Phase 2A:

```bash
python labs/lab6_todo/agent_todo.py --dynamic-observer off \
  "คำถาม"
```

สถานะและผล live proof ระหว่างพัฒนา:

- [Phase 2B progress report](../../artifacts/lab6_phase2b_progress_report.md)
- [Phase 2A vs Phase 2B: first 10-question live run](../../artifacts/lab6_phase2a_phase2b_report.md)
- `artifacts/lab6_phase2a_phase2b_runs.json` contains the raw live outputs and timings
- [Phase 2 failure-case rerun](../../artifacts/lab6_phase2_failure_rerun_report.md)
- `artifacts/lab6_phase2a_phase2b_failure_rerun.json` contains the repeated raw runs
- [Phase 2B completed architecture](../../artifacts/lab6_phase2b_architecture_complete.md)

Phase 2B now makes Python—not the reviewer LLM—the authority for claim
completion, structured `query_more`, tool termination, budgets, and bounded
rewrite. This is architecture-complete but still requires a new live benchmark
before it can be considered better than Phase 2A.

- [Phase 2B architecture live completion report](../../artifacts/lab6_phase2b_completion_live_report.md)

The live report supersedes the “architecture-complete” wording above:
termination and safety are bounded, but provider-dependent planning/rechecking
still prevents operational completion. Phase 2B remains experimental.

- [Full 10-question rerun at commit 4518267](../../artifacts/lab6_phase2_full_rerun_4518267_report.md)
- `artifacts/lab6_phase2_full_rerun_4518267.json` contains all 20 raw runs

The full rerun scored Phase 2A at 5/10 and Phase 2B at 0/10 under strict
grounded grading. Phase 2B must not be merged in its current form.

## Phase 2C: Python-first Observation

Phase 2C replaces the rejected Phase 2B critical path:

```text
Agent calls tool
→ Python checks error / empty / fields / numbers / risk
→ LLM Observer only for semantic-risk
→ answer
```

There is no mandatory Claim Planner, no LLM after every tool result, and no
LLM post-rewrite recheck. Low-risk results and answers stay on the Python path.

- [Phase 2C Python-first report and live smoke](../../artifacts/lab6_phase2c_python_first_report.md)
- `artifacts/lab6_phase2c_python_first_smoke.json` contains the three raw runs

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] ค้นพบ 5 tools

[user] ช่วยทำรายงาน HR: 1) นับพนักงาน... 2) หาพนักงาน... 3) สรุป...
[step 1] TODO_WRITE
[ ] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[ ] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[ ] 3. สรุปข้อค้นพบเชิงธุรกิจ
[step 2] TODO_UPDATE -> {'index': 1, 'status': 'doing'}
...
[step N] TODO_UPDATE -> {'index': 3, 'status': 'done'}
------------------------------------------------------------
[answer]
สรุปข้อค้นพบ: แผนก IT มีพนักงานมากที่สุด...
------------------------------------------------------------
[todo สุดท้าย]
[x] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[x] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[x] 3. สรุปข้อค้นพบเชิงธุรกิจ
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab6_todowrite.png`
