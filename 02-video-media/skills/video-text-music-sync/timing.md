# 时间表与辅助脚本

## 从音乐提取候选

提供明确的输入文件、输出目录与项目帧率。需要安装 FFmpeg。

```bash
python3 scripts/analyze_audio.py --input ./track.wav --out-dir ./analysis --fps 60000/1001
```

输出 JSON 和 CSV，供比较能量变化、瞬态和拍速候选。试听核对乐句、词头与强调点后，再把采用的帧标到时间表。

## 生成合成脚本

将以下示例作为 `timeline.json`。`end_frame` 是排他的结束帧。

```json
{
  "name": "Text timing sample",
  "fps": "60000/1001",
  "width": 1920,
  "height": 1080,
  "duration_frames": 180,
  "texts": [
    {
      "text": "Chapter one",
      "start_frame": 12,
      "end_frame": 135,
      "effect": "fade",
      "position": [0.5, 0.8]
    }
  ]
}
```

```bash
python3 scripts/build_ae.py --timeline ./timeline.json --out-dir ./composition
```

在支持 JSX 的动画合成软件中执行生成的脚本，再检查真实工程和连续预览。遮罩、透视跟踪与手写揭示按镜头制作。路径、字体与媒体源按当前工程设置。
