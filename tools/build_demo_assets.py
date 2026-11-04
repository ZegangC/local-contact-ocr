"""Render public-only demo assets from generated fixtures and a real replay."""

import html
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import demonstrate
from src.fixtures import draw_edit, draw_profile, font, navigation_image, replay_cases

ROOT = Path(__file__).resolve().parents[1]


def build():
    from PIL import Image, ImageDraw
    target = ROOT / "artifacts"
    target.mkdir(exist_ok=True)
    fixtures = replay_cases()
    with tempfile.TemporaryDirectory(prefix="ocr-synthetic-") as tmp:
        result = demonstrate(Path(tmp))
        records = json.loads((Path(tmp) / "联系人.json").read_text(encoding="utf-8"))
    (target / "replay-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "fixture-manifest.json").write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draw_edit(fixtures[0]["edit"]).save(target / "synthetic-edit.png")
    draw_profile(fixtures[0]["profile"]).save(target / "synthetic-profile.png")
    navigation_image().save(target / "synthetic-navigation.png")
    sequence = [
        ("01 读取虚构资料", "输入：代码生成的界面与OCR文本夹具", "先区分昵称、备注和电话。", 0, 0),
        ("02 逐条提交", "已持久化 2 条；下一条尚未提交", "SQLite是真实本地保存，联系人全部虚构。", 2, 0),
        ("03 缺少区域，暂停", "电话栏下边界缺失 / 两次读数不一致", "不能把读取失败写成“没有”。已保存的2条保留。", 2, 2),
        ("04 关闭后恢复任务", "重开数据库；使用修正后的同一虚构输入", "从第3条继续，不重新累计前两条。", 2, 2),
        ("05 续跑与去重", "6条唯一记录；重复身份未新增", "同备注不同身份保留；异常长度不擅自删位。", 6, 3),
        ("06 结束的是样本范围", "离线夹具完成 ≠ 真实通讯录全部完成", "默认演示没有图像OCR、桌面点击或云调用。", 6, 3),
    ]
    frames = []
    for title, subtitle, note, count, index in sequence:
        image = Image.new("RGB", (1000, 680), "#f0f5f7")
        draw = ImageDraw.Draw(image)
        draw.text((30, 20), "LOCAL CONTACT OCR / SYNTHETIC REPLAY", font=font(17), fill="#087f75")
        draw.text((30, 55), title, font=font(31), fill="#183047")
        draw.text((30, 105), subtitle, font=font(19), fill="#415b70")
        panel = draw_edit(fixtures[index]["edit"])
        panel.thumbnail((270, 465))
        image.paste(panel, (32, 155))
        draw.rounded_rectangle((330, 155, 968, 330), radius=12, fill="white")
        draw.text((350, 175), "已保存的虚构联系人", font=font(21), fill="#415b70")
        draw.text((350, 213), str(count), font=font(57), fill="#087f75")
        draw.rounded_rectangle((330, 350, 968, 520), radius=12, fill="white")
        for row, text in enumerate([note[:27], note[27:], "固定规则 + SQLite + 文本导出"]):
            draw.text((350, 375 + row * 38), text, font=font(19), fill="#183047")
        draw.text((330, 555), "合成示意 / 不是微信实录 / 没有真实联系方式", font=font(18), fill="#6a7887")
        draw.text((30, 640), "生成方式：python tools/build_demo_assets.py · 完整结果见离线报告", font=font(16), fill="#6a7887")
        frames.append(image)
    frames[2].save(target / "demo-poster.png")
    frames[0].save(target / "pause-resume-demo.gif", save_all=True, append_images=frames[1:],
                   duration=[1900, 1900, 2800, 2200, 2200, 2800], loop=0, optimize=True)
    rows = "".join("<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in record.values()) + "</tr>" for record in records)
    events = html.escape(json.dumps(result, ensure_ascii=False, indent=2))
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>本地联系人OCR：合成演示报告</title><style>
body{{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;background:#f0f5f7;color:#183047;margin:0}}main{{max-width:1000px;margin:auto;padding:32px 20px}}
h1{{line-height:1.3}}section{{background:white;border-radius:12px;padding:22px;margin:20px 0}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;border-bottom:1px solid #dfe8ec;text-align:left;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.table{{overflow-x:auto}}.notice{{border-left:4px solid #087f75;padding:14px;background:#dff0ed}}@media(max-width:600px){{th,td{{padding:8px}}}}
</style><main><h1>从不确定暂停，到保留进度后续跑</h1><p class="notice">全部界面、昵称、身份与数字为虚构。此处的14秒动画由代码根据实际离线重放结果渲染，不是真实微信操作录像。</p>
<img src="pause-resume-demo.gif" alt="合成演示：保存2条、暂停、恢复至6条并去重">
<section><h2>实际运行的离线结果</h2><p>首次暂停时2条；修正虚构观察后续跑至6条唯一记录；7个输入含1个重复。未调用桌面输入或云OCR。</p>
<div class="table"><table><thead><tr><th>虚构昵称</th><th>虚构备注</th><th>测试数字</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section><h2>状态与事件</h2><details><summary>展开实际重放输出</summary><pre>{events}</pre></details></section>
<section><h2>两个不同的评估层</h2><p>此演示验证结构化OCR读数后的判断、持久化和恢复。真正的图像OCR另由tools/evaluate_ocr.py读取生成面板并统计；不能混为真实界面准确率。历史小批量记录也不代表全通讯录完成。</p></section></main></html>'''
    (target / "demo-report.html").write_text(page, encoding="utf-8")
    print(json.dumps({"synthetic_only": True, "files": sorted(path.name for path in target.iterdir())}, ensure_ascii=True))


if __name__ == "__main__":
    build()
