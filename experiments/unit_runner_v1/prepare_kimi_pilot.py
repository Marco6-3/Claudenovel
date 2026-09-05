"""Prepare an explicit-author-input K3 pilot; no old generated continuation."""
from pathlib import Path
import json
import hashlib


def main():
    source = Path('.local_projects/unit-validation/u002-input/brief.json')
    context = Path('.local_projects/unit-validation/u002-input/前情.md')
    reference = Path('.local_projects/unit-validation/U002_编辑示范_观察转行动.md')
    root = Path('.local_projects/kimi-k3-validation/pilot-input')
    if root.exists():
        raise SystemExit('Use a new output directory; existing pilot inputs are immutable.')
    brief = json.loads(source.read_text(encoding='utf-8'))
    brief.update(max_chars=7999, preferred_chars=6000,
        reader_experience='关心凌默能否在代价有限、不能粗暴伤宿主的条件下救人；每次尝试改变后续选择，结局回应此前困境。',
        relationship_focus='秦思妍有学习、职责和自尊方面的自身考虑。她对凌默的关心通过具体互动、拒绝与回应逐步变得私人，但仍是普通同学，不知完整灵异真相，不表白、不组织处置。主线代价影响相处，相处影响凌默愿不愿意求助。')
    excerpt = reference.read_text(encoding='utf-8').split('---')[1].strip()
    brief['style'] += '\n作者已认可以下叙述密度与人物声音。此片段只作风格参照，不是已经发生的剧情，不得直接复制整段；需重新安排当前单元。\n<style_reference>\n' + excerpt + '\n</style_reference>\n压缩重复笔记与解释，保留真正改变理解的内心描写；通过人物选择与响应建立情感，不用廉价煽情或反复问伤。'
    root.mkdir(parents=True)
    (root/'brief.json').write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding='utf-8')
    (root/'前情.md').write_text(context.read_text(encoding='utf-8'), encoding='utf-8')
    (root/'sources.json').write_text(json.dumps({str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,context,reference)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(root.resolve()))


if __name__ == '__main__':
    main()
