"""
rule_manager.py - 规则管理模块
实现快捷键与目标应用绑定规则的 CRUD，并持久化到 JSON 文件
"""

import json
import os
import sys
import uuid
import logging

logger = logging.getLogger(__name__)


def _get_config_dir():
    """获取配置文件目录：打包后为 .exe 同目录，开发时为脚本所在目录"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # 使用脚本所在目录，而不是当前工作目录
        base = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base, "config")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _get_rules_path():
    """获取 rules.json 完整路径"""
    return os.path.join(_get_config_dir(), "rules.json")


def _default_rules():
    """返回默认规则列表"""
    return []


def load_rules():
    """从 JSON 文件加载规则列表，文件不存在时返回空列表"""
    path = _get_rules_path()
    if not os.path.exists(path):
        return _default_rules()
    try:
        with open(path, "r", encoding="utf-8") as f:
            rules = json.load(f)
            if not isinstance(rules, list):
                return _default_rules()
            return rules
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"加载规则文件失败: {e}")
        return _default_rules()


def save_rules(rules):
    """保存规则列表到 JSON 文件"""
    path = _get_rules_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        logger.info(f"规则已保存到 {path}")
    except OSError as e:
        logger.error(f"保存规则失败: {e}")


def add_rule(name, hotkey, apps):
    """添加新规则，返回新规则字典"""
    rules = load_rules()
    new_rule = {
        "id": str(uuid.uuid4()),
        "name": name,
        "hotkey": hotkey,
        "apps": list(apps),
    }
    rules.append(new_rule)
    save_rules(rules)
    return new_rule


def delete_rule(rule_id):
    """按 ID 删除规则，返回是否成功"""
    rules = load_rules()
    filtered = [r for r in rules if r.get("id") != rule_id]
    if len(filtered) == len(rules):
        return False
    save_rules(filtered)
    return True


def update_rule(rule_id, data):
    """更新指定 ID 的规则，data 为包含更新字段的字典，返回是否成功"""
    rules = load_rules()
    for rule in rules:
        if rule.get("id") == rule_id:
            rule.update(data)
            save_rules(rules)
            return True
    return False
