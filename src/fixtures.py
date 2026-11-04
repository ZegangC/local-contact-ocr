"""Deterministic fictional UI/OCR fixtures. No account or saved screenshots."""

import copy
from pathlib import Path


def line(text, y, x=20, confidence=0.99):
    return {"text": text, "confidence": confidence,
            "box": [[x, y], [x + max(30, len(text) * 18), y],
                    [x + max(30, len(text) * 18), y + 24], [x, y + 24]]}


def profile(name="演示甲", identity="demo_alpha", remark="同名示例"):
    return [line(remark, 20, 110), line("昵称：" + name, 65, 110),
            line("微信号：" + identity, 105, 110), line("备注", 180), line(remark, 180, 110)]


def edit(remark="同名示例", phones=(), complete=True):
    rows = [line("设置备注和标签", 20), line("备注名", 85), line(remark, 125),
            line("标签", 220), line("电话", 285), line("添加电话", 325)]
    rows += [line(phone, 370 + i * 38) for i, phone in enumerate(phones)]
    if complete:
        rows.append(line("描述", 540))
    rows += [line("完成", 740, 40), line("取消", 740, 300)]
    return rows


def sample(name, identity, remark, phones=(), screen=1):
    return {"id": identity, "screen": screen, "profile": profile(name, identity, remark),
            "edit": edit(remark, phones), "edit_alt": edit(remark, phones),
            "expected": {"微信名": name, "备注姓名": remark,
                         "电话号码": "；".join(phones) if phones else "没有"}}


def replay_cases():
    cases = [
        sample("演示甲", "demo_alpha", "同名示例", ["00000000001"]),
        sample("演示乙", "demo_beta", "同名示例"),
        sample("演示丙", "demo_gamma", "边界修复示例", ["000000000003"]),
        sample("演示丁", "demo_delta", "多号码示例", ["00000000004", "00000000005"], 2),
        sample("演示戊", "demo_epsilon", "长备注测试" * 8, ["00000000006"], 2),
        sample("演示己", "demo_zeta", "没有", (), 2),
    ]
    cases[2]["repaired"] = {"edit": copy.deepcopy(cases[2]["edit"])}
    cases[2]["edit"] = edit("边界修复示例", ["000000000003"], complete=False)
    cases[5]["profile"].append(line("添加备注名", 220))
    cases.append(copy.deepcopy(cases[0]))  # Same identity / same data must not duplicate.
    return cases


def ocr_cases():
    """Clean and challenging inputs for actual image OCR, separate from replay."""
    return [
        {"id": "single", "remark": "演示备注", "phones": ["00000000001"], "complete": True, "blur": 0},
        {"id": "empty", "remark": "空值示例", "phones": [], "complete": True, "blur": 0},
        {"id": "multiple", "remark": "多值示例", "phones": ["00000000004", "00000000005"], "complete": True, "blur": 0},
        {"id": "long_digits", "remark": "长度异常示例", "phones": ["000000000003"], "complete": True, "blur": 0},
        {"id": "missing_boundary", "remark": "缺失区域示例", "phones": [], "complete": False, "blur": 0},
        {"id": "blurred", "remark": "模糊示例", "phones": ["00000000007"], "complete": True, "blur": 2.4},
        {"id": "long_remark", "remark": "长备注测试" * 8, "phones": ["00000000008"], "complete": True, "blur": 0},
    ]


def font(size):
    from PIL import ImageFont
    candidates = [Path("C:/Windows/Fonts/msyh.ttc"),
                  Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                  Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("Install a CJK font or configure fixtures.font(); do not benchmark missing-glyph images.")


def draw_edit(rows, blur=0):
    from PIL import Image, ImageDraw, ImageFilter
    image = Image.new("RGB", (440, 800), (43, 43, 43))
    draw = ImageDraw.Draw(image)
    for row in rows:
        x, y = row["box"][0]
        text = row["text"]
        # Wrap fixture content without changing the section boundaries.
        if len(text) > 18:
            for n in range(0, min(len(text), 54), 18):
                draw.text((x, y + (n // 18) * 29), text[n:n + 18], font=font(22), fill="white")
        else:
            draw.text((x, y), text, font=font(22), fill="white")
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return image


def draw_profile(rows):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (440, 300), (43, 43, 43))
    draw = ImageDraw.Draw(image)
    for row in rows:
        draw.text(tuple(row["box"][0]), row["text"][:20], font=font(21), fill="white")
    return image


def navigation_image(identity="demo_alpha", selected=0, rows=(180, 260, 340), tail_noise=False):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (846, 832), (43, 43, 43))
    draw = ImageDraw.Draw(image)
    for i, y in enumerate(rows):
        if i == selected:
            draw.rectangle((105, y, 325, y + 48), fill=(0, 160, 75))
        draw.rectangle((128, y, 169, y + 47), fill=(180, 100 + i * 20, 65))
        draw.text((185, y + 10), "Demo " + str(i), font=ImageFont.load_default(), fill="white")
    draw.text((480, 120), identity, font=ImageFont.load_default(), fill="white")
    if tail_noise:
        draw.rectangle((125, 650, 319, 655), fill="white")
    return image
