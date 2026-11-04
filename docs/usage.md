# 使用与复现

本公开版不控制微信。代码只读取本仓库生成的合成数据，所有结果写入你指定的本地输出目录。

## 基础运行

1. 安装Python及requirements.txt中的Pillow、NumPy；本轮用Python 3.9.13运行，首次安装需要网络。
2. 在仓库根目录执行python demo.py；默认独立目录位于outputs下。
3. 查看控制台first_pass：2条后paused；after_corrected_fixture_resume：6条唯一结果和夹具完成状态。
4. 打开输出目录中的联系人.json、联系人.csv、联系人.xlsx与state.json核对。SQLite是逐条保存的主记录。
5. 运行python -m unittest discover -s tests -v检查合成边界。

可指定python demo.py --output outputs/my-first-demo。新任务要求空目录；重复使用同一目录会明确拒绝覆盖，换一个输出目录即可。

## 查看动画与报告

artifacts/pause-resume-demo.gif是约14秒合成演示；artifacts/demo-report.html可下载后离线打开。两者不依赖登录、外部脚本或真实联系人。可执行python tools/build_demo_assets.py重新生成，字体差异可能使画面像素不同，逻辑数据不变。

## 可选：实际OCR

安装requirements-ocr.txt，再执行python tools/evaluate_ocr.py。程序现场生成7张虚构面板，读取本地RapidOCR模型并做原色/反色两种处理，输出outputs/ocr-evaluation中的图片与JSON。无云端识别或桌面操作。

需要中文字体。默认尝试Windows微软雅黑、Linux Noto CJK或文泉驿，找不到时停止；不要拿缺字方框的图片做有效评估。首次安装模型依赖需要网络，已安装组件和模型后识别路径离线。

## 复核方式

fixtures代码提供测试输入；artifacts/fixture-manifest.json是生成快照，包含预期答案。核心规则不使用expected字段做决定，答案只用于评估。repaired字段是演示显式提供的修正观察，不是模型自动推断。

不要将私人截图放进公开artifacts目录。若在原本地原型处理真实账号，使用原型自己的说明与授权范围，不能把公开重放通过当作实时操作许可。
