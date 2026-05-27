"""Check for documentation drift between root agent_writer and plugins/Claudenovel.

Reports:
- Missing agent_writer module in plugin
- Missing CLI commands in plugin docs
- Skills that reference outdated workflows
"""
from __future__ import annotations

import sys
from pathlib import Path


def check_drift(root: Path) -> dict[str, object]:
    plugin = root / "plugins" / "Claudenovel"
    report: dict[str, object] = {
        "plugin_exists": plugin.exists(),
        "issues": [],
    }
    issues: list[str] = []

    if not plugin.exists():
        issues.append("plugins/Claudenovel 目录不存在")
        report["issues"] = issues
        return report

    # Check agent_writer module
    if not (plugin / "agent_writer").exists():
        issues.append("plugins/Claudenovel 缺少 agent_writer/ 模块")

    if not (plugin / "agent_writer_cli.py").exists():
        issues.append("plugins/Claudenovel 缺少 agent_writer_cli.py")

    # Check AGENT_WRITER.md
    if not (plugin / "AGENT_WRITER.md").exists():
        issues.append("plugins/Claudenovel 缺少 AGENT_WRITER.md")

    # Check skills
    skills_dir = plugin / "skills"
    if skills_dir.exists():
        skill_names = [d.name for d in skills_dir.iterdir() if d.is_dir()]
        report["plugin_skills"] = skill_names

        # Check if any skill mentions agent_writer
        has_aw_skill = any("writer" in s.lower() or "memory" in s.lower() for s in skill_names)
        if not has_aw_skill:
            issues.append("插件 skills 中没有 agent_writer / author-memory 相关 skill")

    # Check root commands
    cli_file = root / "agent_writer" / "cli.py"
    if cli_file.exists():
        content = cli_file.read_text(encoding="utf-8")
        import re
        commands = re.findall(r'sub\.add_parser\("([^"]+)"', content)
        report["root_commands"] = commands

        # Check plugin README/skills for mentions
        plugin_docs = []
        for md_file in plugin.rglob("*.md"):
            try:
                plugin_docs.append(md_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        plugin_text = "\n".join(plugin_docs)

        missing_in_docs = []
        for cmd in commands:
            if cmd not in plugin_text:
                missing_in_docs.append(cmd)
        if missing_in_docs:
            issues.append(f"根目录 CLI 命令在插件文档中缺失: {', '.join(missing_in_docs)}")

    # Check root AGENT_WRITER.md vs plugin
    root_aw = root / "AGENT_WRITER.md"
    plugin_aw = plugin / "AGENT_WRITER.md"
    if root_aw.exists() and plugin_aw.exists():
        root_text = root_aw.read_text(encoding="utf-8")
        plugin_text = plugin_aw.read_text(encoding="utf-8")
        if root_text != plugin_text:
            issues.append("AGENT_WRITER.md 内容不一致")
    elif root_aw.exists() and not plugin_aw.exists():
        issues.append("根目录有 AGENT_WRITER.md 但插件没有")

    report["issues"] = issues
    report["issue_count"] = len(issues)
    return report


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    report = check_drift(root)

    print(f"插件存在: {report['plugin_exists']}")
    print(f"问题数: {report['issue_count']}")
    print()
    for issue in report["issues"]:
        print(f"  - {issue}")

    if "root_commands" in report:
        print(f"\n根目录命令: {', '.join(report['root_commands'])}")
    if "plugin_skills" in report:
        print(f"插件 skills: {', '.join(report['plugin_skills'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
