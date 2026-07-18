"""
Lab 5 — Skill System (SkillLoader) ตามหลัก Progressive Disclosure + Routing
อ้างอิง outline: บทที่ 2.1 / แบบฝึกหัดที่ 5

SkillLoader:
  - อ่านเฉพาะ "ชื่อ + คำอธิบายสั้น" ของทุก skill ใส่ใน system prompt (Progressive
    Disclosure) — ไม่ยัดเนื้อหาเต็มทุก skill ลง context
  - โหลดเนื้อหาเต็มเฉพาะ skill ที่ถูก route ไปเท่านั้น (ประหยัด token + พฤติกรรมคงเส้น)

อ้างอิงแนวคิด Anthropic (Context Engineering / Building Effective Agents)
"""
import os
import re

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")


def _parse_front_matter(text: str) -> dict:
    """แกะ front-matter YAML แบบง่าย (name, description) จากหัวไฟล์ SKILL.md."""
    meta = {"name": "", "description": ""}
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return meta
    block = m.group(1)
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+)$", block, re.MULTILINE)
        if km:
            meta[key] = km.group(1).strip()
    return meta


class SkillLoader:
    def __init__(self, skills_dir: str = SKILLS_DIR):
        self.skills_dir = skills_dir
        self._skills: dict[str, dict] = {}   # name -> {description, path}
        self._scan()

    def _scan(self):
        for entry in sorted(os.listdir(self.skills_dir)):
            path = os.path.join(self.skills_dir, entry, "SKILL.md")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    meta = _parse_front_matter(f.read())
                name = meta["name"] or entry
                self._skills[name] = {"description": meta["description"], "path": path}

    # ---- Progressive Disclosure : ใส่แค่ชื่อ+คำอธิบายลง system prompt ----
    def index_for_prompt(self) -> str:
        lines = ["Skills ที่ใช้ได้ (เลือกใช้ให้ตรงกับคำถาม):"]
        for name, info in self._skills.items():
            lines.append(f"- {name}: {info['description']}")
        lines.append(
            "\nก่อนตอบ ให้เลือก skill ที่ตรงที่สุด 1 ตัว โดยขึ้นบรรทัดแรกว่า "
            "'SKILL: <ชื่อ skill>' แล้วค่อยทำงานตามเนื้อหา skill นั้น"
        )
        return "\n".join(lines)

    def names(self) -> list[str]:
        return list(self._skills.keys())

    # ---- โหลดเนื้อหาเต็ม เฉพาะ skill ที่ถูก route ----
    def load_full(self, name: str) -> str:
        info = self._skills.get(name)
        if not info:
            return ""
        with open(info["path"], encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def route_from_reply(reply: str) -> str | None:
        """อ่านบรรทัด 'SKILL: xxx' ที่ LLM เลือก."""
        m = re.search(r"SKILL:\s*([a-zA-Z_]+)", reply or "")
        return m.group(1).strip() if m else None
