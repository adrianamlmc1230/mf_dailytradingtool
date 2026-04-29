"""盘口标准化模块"""

import re
from typing import Optional


class HandicapNormalizer:
    """盘口标准化器"""

    # 盘口映射表
    HANDICAP_MAP = {
        # === 基础盘口 ===
        "平手": 0.0,
        "平/半": 0.25, "平手/半球": 0.25,
        "半球": 0.5,
        "半/一": 0.75, "半球/一球": 0.75,
        "一球": 1.0,
        "一/球半": 1.25, "一球/球半": 1.25,
        "球半": 1.5,
        # === 1.75 ~ 6.0 繁体 ===
        "球半/兩球": 1.75, "兩球": 2.0,
        "兩球/兩球半": 2.25, "兩球半": 2.5,
        "兩球半/三球": 2.75, "三球": 3.0,
        "三球/三球半": 3.25, "三球半": 3.5,
        "三球半/四球": 3.75, "四球": 4.0,
        "四球/四球半": 4.25, "四球半": 4.5,
        "四球半/五球": 4.75, "五球": 5.0,
        "五球/五球半": 5.25, "五球半": 5.5,
        "五球半/六球": 5.75, "六球": 6.0,
        # === 1.75 ~ 6.0 简体 ===
        "球半/两": 1.75, "球半/两球": 1.75, "两球": 2.0,
        "两球/两球半": 2.25, "两球半": 2.5,
        "两球半/三球": 2.75, "三球": 3.0,
        "三球/三球半": 3.25, "三球半": 3.5,
        "三球半/四球": 3.75, "四球": 4.0,
        "四球/四球半": 4.25, "四球半": 4.5,
        "四球半/五球": 4.75, "五球": 5.0,
        "五球/五球半": 5.25, "五球半": 5.5,
        "五球半/六球": 5.75, "六球": 6.0,
    }

    @classmethod
    def normalize(cls, text: str) -> Optional[float]:
        """标准化盘口文本为数值

        Args:
            text: 原始盘口文本，如 "半球", "平/半", "受半球"

        Returns:
            标准化后的数值，如 0.5, 0.25, -0.5
            无法解析时返回 None
        """
        if not text:
            return None

        # 清理文本
        t = text.strip().replace(" ", "")

        # 处理"受让"前缀
        prefix = 1
        if "受让" in t or "受讓" in t:
            prefix = -1
            t = t.replace("受让", "").replace("受讓", "")
        elif "受" in t:
            prefix = -1
            t = t.replace("受", "")

        # 1. 查表法
        if t in cls.HANDICAP_MAP:
            return cls.HANDICAP_MAP[t] * prefix

        # 2. 数字型盘口解析
        if "/" in t:
            # 分数盘口，如 "2.5/3"
            try:
                parts = t.split("/")
                if len(parts) == 2:
                    lower = float(parts[0])
                    upper = float(parts[1])
                    return ((lower + upper) / 2) * prefix
            except (ValueError, IndexError):
                pass
        else:
            # 整数或小数盘口
            try:
                return float(t) * prefix
            except ValueError:
                pass

        return None

    @classmethod
    def parse_handicap_raw(cls, text: str) -> tuple[Optional[float], str]:
        """解析盘口，同时返回标准化值和原始文本

        Returns:
            (标准化值, 原始盘口文本)
        """
        normalized = cls.normalize(text)
        return normalized, text.strip() if text else ""