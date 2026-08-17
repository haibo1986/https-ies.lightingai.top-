from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Any


def _lerp(a: float, b: float, ratio: float) -> float:
    return a + (b - a) * ratio


@dataclass
class PhotometricEngine:
    """Single LM-63 Type-C interpolation source for reports and validation."""

    vertical: list[float]
    horizontal: list[float]
    values: list[list[float]]

    @classmethod
    def from_parsed(cls, parsed: dict[str, Any]) -> "PhotometricEngine":
        if int(parsed["photometric_type"]) != 1:
            raise ValueError("专业报告图表目前仅支持 LM-63 Type C 光度坐标。")
        multiplier = float(parsed["candela_multiplier"])
        horizontal = list(map(float, parsed["horizontal_angles"]))
        values = [[float(v) * multiplier for v in row] for row in parsed["candela_values"]]
        # C360 is the same direction as C0 and must not receive double weight.
        if len(horizontal) > 1 and abs(horizontal[-1] - horizontal[0] - 360) < 1e-6:
            horizontal, values = horizontal[:-1], values[:-1]
        return cls(list(map(float, parsed["vertical_angles"])), horizontal, values)

    def _gamma_value(self, row: list[float], gamma: float) -> float:
        gamma = min(max(float(gamma), self.vertical[0]), self.vertical[-1])
        pos = bisect.bisect_right(self.vertical, gamma)
        if pos == 0: return row[0]
        if pos >= len(self.vertical): return row[-1]
        lo, hi = pos - 1, pos
        span = self.vertical[hi] - self.vertical[lo]
        return _lerp(row[lo], row[hi], (gamma - self.vertical[lo]) / span if span else 0)

    def _symmetry_angle(self, c_angle: float) -> float:
        c = c_angle % 360
        if len(self.horizontal) == 1:
            return self.horizontal[0]
        last = self.horizontal[-1]
        if last <= 90 + 1e-6:
            folded = c % 180
            return 180 - folded if folded > 90 else folded
        if last <= 180 + 1e-6:
            return 360 - c if c > 180 else c
        return c

    def intensity(self, c_angle: float, gamma: float) -> float:
        c = self._symmetry_angle(c_angle)
        if len(self.horizontal) == 1:
            return self._gamma_value(self.values[0], gamma)
        # Full distributions interpolate periodically between the last plane and C0.
        if self.horizontal[-1] > 180 + 1e-6:
            angles = self.horizontal + [self.horizontal[0] + 360]
            rows = self.values + [self.values[0]]
            if c < angles[0]: c += 360
        else:
            angles, rows = self.horizontal, self.values
        pos = bisect.bisect_right(angles, c)
        if pos == 0: return self._gamma_value(rows[0], gamma)
        if pos >= len(angles): return self._gamma_value(rows[-1], gamma)
        lo, hi = pos - 1, pos
        a = self._gamma_value(rows[lo], gamma); b = self._gamma_value(rows[hi], gamma)
        span = angles[hi] - angles[lo]
        return _lerp(a, b, (c - angles[lo]) / span if span else 0)

    def axis_profile(self, positive_c: float, negative_c: float, step: float = 1) -> list[tuple[float, float]]:
        samples = []
        angle = -90.0
        while angle <= 90 + 1e-9:
            plane = negative_c if angle < 0 else positive_c
            samples.append((round(angle, 6), self.intensity(plane, abs(angle))))
            angle += step
        return samples

    def integrated_flux(self, gamma_max: float = 90, step: float = 1) -> float:
        total = 0.0
        c = 0.0
        dc = math.radians(step)
        dg = math.radians(step)
        while c < 360 - 1e-9:
            gamma = 0.0
            while gamma < gamma_max - 1e-9:
                cm, gm = c + step / 2, gamma + step / 2
                total += self.intensity(cm, gm) * math.sin(math.radians(gm)) * dc * dg
                gamma += step
            c += step
        return total

    def mean_intensity(self, gamma: float, c_step: float = 1) -> float:
        samples = [self.intensity(c, gamma) for c in range(0, 360, max(1, int(c_step)))]
        return sum(samples) / len(samples) if samples else 0.0

    def zonal_flux(self, zone_size: float = 5, step: float = 1) -> list[dict[str, float]]:
        """Integrate Type-C intensity over successive lower-hemisphere zones."""
        zones: list[dict[str, float]] = []
        cumulative = 0.0
        start = 0.0
        while start < 90 - 1e-9:
            end = min(90.0, start + zone_size)
            flux = self.integrated_flux(end, step) - self.integrated_flux(start, step)
            cumulative += flux
            zones.append({
                "start_angle": start,
                "end_angle": end,
                "gamma_angle": end,
                "mean_intensity_cd": self.mean_intensity(end),
                "flux_lm": flux,
                "cumulative_lm": cumulative,
                "percent": 0.0,
            })
            start = end
        total = cumulative or 1.0
        for zone in zones:
            zone["percent"] = zone["flux_lm"] / total * 100
        return zones

    def horizontal_illuminance(self, x: float, y: float, height: float) -> float:
        rho = math.hypot(x, y); gamma = math.degrees(math.atan2(rho, height))
        c_angle = math.degrees(math.atan2(y, x)) % 360
        return self.intensity(c_angle, gamma) * math.cos(math.radians(gamma)) ** 3 / (height * height)

    def spatial_illuminance(self, x: float, depth: float, c_plane: float = 0) -> float:
        distance = math.hypot(x, depth)
        if distance <= 1e-9: return 0.0
        gamma = math.degrees(math.atan2(abs(x), depth))
        plane = c_plane if x >= 0 else (c_plane + 180) % 360
        return self.intensity(plane, gamma) / (distance * distance)

    def luminance(self, c_angle: float, gamma: float, luminous_area_m2: float) -> float:
        projected = luminous_area_m2 * max(math.cos(math.radians(gamma)), 0.01)
        return self.intensity(c_angle, gamma) / projected

    def grid(self, extent: float, count: int, sampler) -> tuple[list[float], list[float], list[list[float]]]:
        coords = [-extent + 2 * extent * i / (count - 1) for i in range(count)]
        return coords, coords, [[sampler(x, y) for x in coords] for y in coords]


def contour_segments(xs: list[float], ys: list[float], grid: list[list[float]], level: float) -> list[tuple[tuple[float,float],tuple[float,float]]]:
    """Marching-squares contour segments in physical grid coordinates."""
    segments = []
    edge_pairs = {1:[(3,0)],2:[(0,1)],3:[(3,1)],4:[(1,2)],5:[(3,2),(0,1)],6:[(0,2)],7:[(3,2)],8:[(2,3)],9:[(0,2)],10:[(0,3),(1,2)],11:[(1,2)],12:[(1,3)],13:[(0,1)],14:[(3,0)]}
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            pts=[(xs[i],ys[j]),(xs[i+1],ys[j]),(xs[i+1],ys[j+1]),(xs[i],ys[j+1])]
            vals=[grid[j][i],grid[j][i+1],grid[j+1][i+1],grid[j+1][i]]
            case=sum((1<<k) for k,v in enumerate(vals) if v>=level)
            if case in (0,15): continue
            def cross(edge):
                a,b=((0,1),(1,2),(2,3),(3,0))[edge]; span=vals[b]-vals[a]
                ratio=(level-vals[a])/span if span else .5
                return (_lerp(pts[a][0],pts[b][0],ratio),_lerp(pts[a][1],pts[b][1],ratio))
            for first,second in edge_pairs.get(case,[]): segments.append((cross(first),cross(second)))
    return segments
