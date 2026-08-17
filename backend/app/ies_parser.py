from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


class IESParseError(ValueError):
    """IES 文件无法安全解析。"""


class IESParser:
    SUPPORTED_VERSIONS = {"IESNA:LM-63-1995", "IESNA:LM-63-2002"}
    NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")

    @classmethod
    def parse(cls, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="gbk")
            except (UnicodeDecodeError, OSError):
                try:
                    text = path.read_text(encoding="latin-1")
                except OSError as exc:
                    raise IESParseError(f"无法读取 IES 文件：{exc}") from exc
        except OSError as exc:
            raise IESParseError(f"无法读取 IES 文件：{exc}") from exc

        lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            raise IESParseError("IES 文件为空。")

        version = lines[0].lstrip("\ufeff")
        if version not in cls.SUPPORTED_VERSIONS:
            raise IESParseError("仅支持 IESNA:LM-63-1995 和 IESNA:LM-63-2002。")

        tilt_index = next((i for i, line in enumerate(lines) if line.upper().startswith("TILT=")), None)
        if tilt_index is None:
            raise IESParseError("缺少 TILT 字段。")
        tilt_value = lines[tilt_index].split("=", 1)[1].strip().upper()
        if tilt_value == "INCLUDE":
            raise IESParseError("暂不支持 TILT=INCLUDE。")
        if tilt_value != "NONE":
            raise IESParseError("暂不支持 TILT=FILE，仅支持 TILT=NONE。")

        header_lines = lines[1:tilt_index]
        keywords: dict[str, str] = {}
        for line in header_lines:
            match = re.match(r"^\[([^]]+)]\s*(.*)$", line)
            if match:
                keywords[match.group(1).strip()] = match.group(2).strip()

        raw_tokens = " ".join(lines[tilt_index + 1 :]).split()
        if not raw_tokens:
            raise IESParseError("TILT 字段后缺少数字数据。")
        invalid = next((token for token in raw_tokens if not cls.NUMBER_RE.fullmatch(token)), None)
        if invalid is not None:
            raise IESParseError(f"IES 数字字段包含非法值：{invalid}")
        numbers = [float(token) for token in raw_tokens]
        if not all(math.isfinite(value) for value in numbers):
            raise IESParseError("IES 数字字段不能包含无限值或 NaN。")
        if len(numbers) < 13:
            raise IESParseError("IES 数字字段数量不完整。")

        integer_fields = {
            "number_of_lamps": numbers[0],
            "num_vertical_angles": numbers[3],
            "num_horizontal_angles": numbers[4],
            "photometric_type": numbers[5],
            "units_type": numbers[6],
        }
        for name, value in integer_fields.items():
            if not value.is_integer():
                raise IESParseError(f"字段 {name} 必须是整数。")

        number_of_lamps = int(numbers[0])
        num_vertical = int(numbers[3])
        num_horizontal = int(numbers[4])
        if number_of_lamps <= 0:
            raise IESParseError("灯泡数量必须大于 0。")
        if num_vertical <= 0:
            raise IESParseError("垂直角数量必须大于 0。")
        if num_horizontal <= 0:
            raise IESParseError("水平角数量必须大于 0。")
        lumens_per_lamp = numbers[1]
        if lumens_per_lamp != -1 and lumens_per_lamp <= 0:
            raise IESParseError("每灯光通量必须大于 0，绝对光度文件应使用 -1。")
        if numbers[2] <= 0:
            raise IESParseError("candela_multiplier 必须大于 0。")
        if int(numbers[5]) not in {1, 2, 3}:
            raise IESParseError("photometric_type 必须是 1、2 或 3。")
        if int(numbers[6]) not in {1, 2}:
            raise IESParseError("units_type 必须是 1 或 2。")
        if any(value < 0 for value in numbers[7:10]):
            raise IESParseError("灯具尺寸不能为负数。")
        if numbers[10] <= 0:
            raise IESParseError("ballast_factor 必须大于 0。")
        if numbers[12] < 0:
            raise IESParseError("input_watts 不能为负数。")

        expected = 13 + num_vertical + num_horizontal + num_vertical * num_horizontal
        if len(numbers) != expected:
            raise IESParseError(
                f"IES 数字字段数量不匹配：应为 {expected}，实际为 {len(numbers)}；"
                "请检查角度和 candela 数据。"
            )

        cursor = 13
        vertical_angles = numbers[cursor : cursor + num_vertical]
        cursor += num_vertical
        horizontal_angles = numbers[cursor : cursor + num_horizontal]
        cursor += num_horizontal
        flat_candela = numbers[cursor:]
        candela_values = [
            flat_candela[row * num_vertical : (row + 1) * num_vertical]
            for row in range(num_horizontal)
        ]

        if any(b < a for a, b in zip(vertical_angles, vertical_angles[1:])):
            raise IESParseError("垂直角必须按升序排列。")
        if any(b < a for a, b in zip(horizontal_angles, horizontal_angles[1:])):
            raise IESParseError("水平角必须按升序排列。")
        if any(angle < 0 or angle > 180 for angle in vertical_angles):
            raise IESParseError("垂直角必须位于 0 到 180 度之间。")
        if any(angle < 0 or angle > 360 for angle in horizontal_angles):
            raise IESParseError("水平角必须位于 0 到 360 度之间。")
        if any(value < 0 for value in flat_candela):
            raise IESParseError("candela 数据不能包含负数。")

        suggested_flux = number_of_lamps * lumens_per_lamp if lumens_per_lamp > 0 else None
        return {
            "ies_version": version,
            "header_lines": header_lines,
            "keywords": keywords,
            "tilt_type": "NONE",
            "number_of_lamps": number_of_lamps,
            "lumens_per_lamp": lumens_per_lamp,
            "candela_multiplier": numbers[2],
            "num_vertical_angles": num_vertical,
            "num_horizontal_angles": num_horizontal,
            "photometric_type": int(numbers[5]),
            "units_type": int(numbers[6]),
            "width": numbers[7],
            "length": numbers[8],
            "height": numbers[9],
            "ballast_factor": numbers[10],
            "future_use": numbers[11],
            "input_watts": numbers[12],
            "ballast_lamp_photometric_factor": numbers[11],
            "vertical_angles": vertical_angles,
            "horizontal_angles": horizontal_angles,
            "candela_values": candela_values,
            "max_candela": max(flat_candela) * numbers[2],
            "original_file_name": path.name,
            "is_absolute_photometry": lumens_per_lamp == -1,
            "supports_auto_conversion": suggested_flux is not None,
            "suggested_source_luminous_flux_lm": suggested_flux,
        }
