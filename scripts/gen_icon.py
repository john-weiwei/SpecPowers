# -*- coding: utf-8 -*-
"""SpecPowers 插件图标生成脚本（v2 设计稿）。

设计理念（UI 视角）：
  - 主体：五段圆弧拼成闭环圆环 —— 五阶段（init→explore→propose→apply→archive）
    的闭环流水线；弧段间等间隙，512px 与 32px 下均可辨读
  - 记忆点：中心粗壮圆头对钩 —— 「规格驱动、闭环完成」的唯一视觉锚点
  - 强调色：仅第五段（archive）用青色点亮，与白环形成「四段完成 + 一段收尾」
    的节奏，全图只有两种前景色，克制不花哨
  - 体积感：indigo→violet 对角渐变底 + 顶部白色高光层 + 底部轻微压暗，
    亚光立体质感；64×64 小图渐变放大无损（线性函数不引入误差）
  - 抗锯齿：4 倍超采样绘制后 LANCZOS 缩小

替换图标只需重跑本脚本并推送（市场 icon URL 引用 @main 自动指向新文件）。

作者：张威威(005819)  日期：2026-09-24  AI 工具：ZCode (GLM-5.3)
"""

import math
import os

from PIL import Image, ImageDraw

# 输出尺寸与超采样倍数
FINAL_SIZE = 512
SS = 4
CANVAS = FINAL_SIZE * SS

# 配色：对角渐变（左上 → 右下）与强调色
BG_TOP_LEFT = (79, 70, 229)
BG_BOTTOM_RIGHT = (139, 92, 246)
ACCENT = (165, 243, 252)
WHITE = (255, 255, 255, 255)

# 圆环几何：半径/线宽占画布比例、段数与间隙角
RING_R_RATIO = 0.40
RING_W_RATIO = 0.135
SEG_COUNT = 5
GAP_DEG = 16.0

# 仓库内输出路径
OUTPUT = "plugins/specpowers/assets/icon.png"


def _gradient_layer(size, c_from, c_to, diagonal=True):
    """生成对角（或垂直）线性渐变 RGBA 图：小尺寸逐像素计算后无损放大。"""
    small = 64
    grad = Image.new("RGBA", (small, small))
    px = grad.load()
    for y in range(small):
        for x in range(small):
            # 对角渐变按 (x+y) 归一化取 t，垂直渐变仅按 y
            t = (x + y) / (2 * (small - 1)) if diagonal else y / (small - 1)
            r = round(c_from[0] + (c_to[0] - c_from[0]) * t)
            g = round(c_from[1] + (c_to[1] - c_from[1]) * t)
            b = round(c_from[2] + (c_to[2] - c_from[2]) * t)
            px[x, y] = (r, g, b, 255)
    return grad.resize((size, size), Image.BICUBIC)


def _alpha_fade_layer(size, top_alpha, bottom_alpha=0):
    """生成垂直透明度渐变的白色叠加层（顶部高光用）。"""
    small = 64
    fade = Image.new("L", (1, small))
    for y in range(small):
        t = y / (small - 1)
        a = round(top_alpha + (bottom_alpha - top_alpha) * t)
        fade.putpixel((0, y), a)
    fade = fade.resize((size, size), Image.BICUBIC)
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    layer.putalpha(fade)
    return layer


def build_background():
    """构建背景：对角渐变 + 顶部高光 + 底部微压暗，裁成圆角方块。"""
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    base = _gradient_layer(CANVAS, BG_TOP_LEFT, BG_BOTTOM_RIGHT, diagonal=True)
    canvas.paste(base, (0, 0))

    # 顶部 30% 区域白色高光（营造左上光源体积感）
    highlight = _alpha_fade_layer(CANVAS, top_alpha=36)
    canvas = Image.alpha_composite(canvas, _crop_to_band(highlight, 0.0, 0.34))
    # 底部 25% 区域黑色轻压（收住底部，避免头重脚轻）
    darken = _alpha_fade_layer(CANVAS, top_alpha=0)
    darken = darken.transpose(Image.FLIP_TOP_BOTTOM)
    darken = _recolor(darken, (18, 10, 60))
    canvas = Image.alpha_composite(canvas, _crop_to_band(darken, 0.78, 1.0, max_alpha=42))

    # 圆角蒙版裁形
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, CANVAS - 1, CANVAS - 1], radius=round(CANVAS * 0.21), fill=255)
    rounded = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    rounded.paste(canvas, (0, 0), mask)
    return rounded


def _crop_to_band(layer, start_ratio, end_ratio, max_alpha=255):
    """把全幅透明度层裁剪到纵向条带（条带外 alpha 清零），并可选限制最大 alpha。"""
    alpha = layer.split()[3]
    top = round(CANVAS * start_ratio)
    bottom = round(CANVAS * end_ratio)
    band = Image.new("L", (CANVAS, CANVAS), 0)
    band.paste(alpha.crop((0, top, CANVAS, bottom)), (0, top))
    if max_alpha < 255:
        band = band.point(lambda a: round(a * max_alpha / 255))
    out = layer.copy()
    out.putalpha(band)
    return out


def _recolor(layer, rgb):
    """把单色透明层换成指定颜色（保留 alpha 通道）。"""
    r, g, b, a = layer.split()
    solid = Image.new("RGBA", layer.size, (*rgb, 0))
    solid.putalpha(a)
    return solid


def _round_line(draw, p1, p2, color, width):
    """绘制圆头粗线段：线体 + 两端圆帽。"""
    draw.line([p1, p2], fill=color, width=width)
    r = width / 2
    for p in (p1, p2):
        cx, cy = p
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def draw_ring_and_check(img):
    """绘制五段闭环圆环（末段青色）与中心白色圆头对钩。"""
    draw = ImageDraw.Draw(img)
    cx = cy = CANVAS / 2
    ring_r = CANVAS * RING_R_RATIO
    ring_w = round(CANVAS * RING_W_RATIO)
    seg_deg = (360.0 - SEG_COUNT * GAP_DEG) / SEG_COUNT
    cap_r = ring_w / 2

    # 从顶部（-90°）起顺时针逐段绘制，末段用强调青色
    start = -90.0 + GAP_DEG / 2
    for i in range(SEG_COUNT):
        s = start + i * (seg_deg + GAP_DEG)
        e = s + seg_deg
        color = ACCENT + (255,) if i == SEG_COUNT - 1 else WHITE
        bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
        draw.arc(bbox, start=s, end=e, fill=color, width=ring_w)
        # 两端圆帽（PIL arc 为方头）
        for deg in (s, e):
            rad = math.radians(deg)
            px = cx + ring_r * math.cos(rad)
            py = cy + ring_r * math.sin(rad)
            draw.ellipse([px - cap_r, py - cap_r, px + cap_r, py + cap_r], fill=color)

    # 中心白色圆头对钩（单位坐标 × 环半径，视觉重心略上移）
    p1 = (cx - ring_r * 0.34, cy + ring_r * 0.06)
    p2 = (cx - ring_r * 0.08, cy + ring_r * 0.32)
    p3 = (cx + ring_r * 0.40, cy - ring_r * 0.26)
    check_w = round(ring_w * 0.92)
    _round_line(draw, p1, p2, WHITE, check_w)
    _round_line(draw, p2, p3, WHITE, check_w)


def main():
    """生成图标并写盘。"""
    img = build_background()
    draw_ring_and_check(img)
    img = img.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    img.save(OUTPUT, "PNG")
    print("图标已生成：" + OUTPUT)


if __name__ == "__main__":
    main()
