# -*- coding: utf-8 -*-
"""机器翻译流水线：把指令库里的英文官方说明翻成中文，写入 data/mt_cache.json。

翻译源：MyMemory 免费翻译 API（GET，无需 Key，单次上限 500 字符）。
策略：
  1. 只对「需要修复」的条目发起请求（规则翻译不合格 / 仍是英文原文）；
  2. 按英文原文去重，同一条说明只翻一次（实测可省掉约一半请求）；
  3. 结果先做 CS2 术语规范化，再落盘缓存；
  4. 断点续传：已缓存的直接跳过；限流时退避重试。

用法：
  python tools/translate_db.py --priority-core   # 只翻实用指令（k=1）
  python tools/translate_db.py --priority-rest   # 只翻其余可翻译条目
  python tools/translate_db.py --priority all    # 全部
  python tools/translate_db.py --stats           # 只看进度，不发请求
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "mt_cache.json"
API = "https://api.mymemory.translated.net/get?q={}&langpair=en|zh-CN&de=contact-in-repo"


def norm_zh(text: str) -> str:
    """CS2 术语规范化：把机翻的通用译法换成玩家习惯说法。"""
    t = text.strip()
    fixes = [
        (r"布娃娃(?:玩家|模型|尸体)?", "尸体模型"),
        (r"布娃娃", "尸体模型"),
        (r"玩偶", "尸体模型"),
        (r"[Xx]\s*射线", "X 光"),
        (r"观察(?:者|员)", "观战者"),
        (r"旁观(?:者|人员)", "观战者"),
        (r"观众", "观战者"),
        (r"即时重放", "死亡回放"),
        (r"杀手回放", "击杀回放"),
        (r"杀戮回放", "击杀回放"),
        (r"雷达缩放比例", "雷达缩放"),
        (r"SourceTV", "SourceTV（HLTV）"),
        (r"HLTV", "HLTV"),
        (r"反恐精英：全球攻势", "CS2"),
        (r"计数器-打击", "CS2"),
        (r"控制台变量", "控制台变量"),
        (r"控制台命令", "控制台指令"),
        (r"服务器端变量", "服务器变量"),
        (r"插值比率", "插值比例"),
        (r"客户(?:端|机|们)?", "客户端"),
        (r"服务端", "服务器端"),
        (r"机器人程序", "机器人 Bot"),
        (r"机器人", "机器人 Bot"),
        (r"计算机玩家", "机器人 Bot"),
        (r"电脑玩家", "机器人 Bot"),
        (r"手榴弹", "手雷/投掷物"),
        (r"手雷", "投掷物"),
        (r"闪光(?:弹|手榴弹)", "闪光弹"),
        (r"烟幕(?:弹)?", "烟雾弹"),
        (r"燃烧瓶", "燃烧瓶"),
        (r"狙击手步枪", "狙击枪"),
        (r"狙击步枪", "狙击枪"),
        (r"机关枪", "机枪"),
        (r"冲锋枪", "冲锋枪"),
        (r"霰弹枪", "霰弹枪"),
        (r"防弹衣", "护甲"),
        (r"头盔", "头盔"),
        (r"生命值", "生命值"),
        (r"延迟补偿", "延迟补偿"),
        (r"滞后补偿", "延迟补偿"),
        (r"视野范围", "视野范围"),
        (r"视场", "视野范围"),
        (r"帧速率", "帧率"),
        (r"帧每秒", "帧率"),
        (r"帧秒", "帧率"),
        (r"每秒帧数", "帧率"),
        (r"垂直同步", "垂直同步"),
        (r"抗锯齿", "抗锯齿"),
        (r"纹理过滤", "纹理过滤"),
        (r"各向异性过滤", "各向异性过滤"),
        (r"阴影贴图", "阴影贴图"),
        (r"控制台输出", "控制台输出"),
        (r"回放", "回放"),
        (r"演示(?:文件|录像)?", "录像"),
        (r"演示", "录像"),
        (r"重放", "回放"),
        (r"语音聊天", "语音通话"),
        (r"聊天栏", "聊天框"),
        (r"准星", "准星"),
        (r"十字准线", "准星"),
        (r"十字准星", "准星"),
        (r"雷达", "雷达"),
        (r"小地图", "小地图"),
        (r"记分板", "计分板"),
        (r"得分板", "计分板"),
        (r"击杀信息", "击杀提示"),
        (r"杀戮", "击杀"),
        (r"死亡竞赛", "死斗模式"),
        (r"热身", "热身"),
        (r"冻结时间", "冻结时间"),
        (r"拆弹", "拆弹"),
        (r"解救人质", "解救人质"),
        (r"特警", "反恐精英（CT）"),
        (r"恐怖分子", "恐怖分子（T）"),
        (r"团队", "队伍"),
        (r"金币", "金钱"),
        (r"美元", "金钱"),
        (r"购买菜单", "购买菜单"),
        (r"热键", "快捷键"),
        (r"键盘绑定", "按键绑定"),
        (r"键绑定", "按键绑定"),
        (r"绑定键", "按键绑定"),
        (r"鼠标灵敏度", "鼠标灵敏度"),
        (r"鼠标加速", "鼠标加速"),
        (r"原始输入", "原始输入"),
        (r"轮询率", "轮询率"),
        (r"垂直同步", "垂直同步"),
        (r"无边框窗口模式", "无边框窗口"),
        (r"全屏模式", "全屏"),
        (r"分辨率", "分辨率"),
        (r"纵横比", "画面比例"),
        (r"宽高比", "画面比例"),
        (r"高动态范围", "HDR 高动态范围"),
        (r"环境光遮蔽", "环境光遮蔽"),
        (r"后期处理", "后期处理"),
        (r"色调映射", "色调映射"),
        (r"动态模糊", "动态模糊"),
        (r"景深", "景深"),
        (r"粒子效果", "粒子特效"),
        (r"粒子", "粒子"),
        (r"贴花", "弹痕贴花"),
        (r"贴纸", "贴花"),
        (r"命中盒", "命中判定框"),
        (r"命中组", "命中部位"),
        (r"射线(?:追踪|投射)?", "射线检测"),
        (r"视线", "视线"),
        (r"导航网格", "导航网格"),
        (r"实体", "实体"),
        (r"碰撞", "碰撞"),
        (r"物理(?:学)?", "物理"),
        (r"调试(?:信息|输出)?", "调试"),
        (r"开发(?:者)?模式", "开发者模式"),
        (r"统计数据", "统计数据"),
        (r"性能分析", "性能分析"),
        (r"基准测试", "基准测试"),
        (r"日志文件", "日志文件"),
        (r"配置文件", "配置文件"),
        (r"初始化", "初始化"),
        (r"卸载", "卸载"),
        (r"预加载", "预载"),
        (r"缓存", "缓存"),
        (r"线程", "线程"),
        (r"异步", "异步"),
        (r"渲染器", "渲染器"),
        (r"着色器", "着色器"),
        (r"顶点", "顶点"),
        (r"像素", "像素"),
        (r"多边形", "多边形"),
        (r"几何(?:体|形状)?", "几何体"),
        (r"天空盒", "天空盒"),
        (r"环境立方体贴图", "环境立方体贴图"),
        (r"泛光", "泛光"),
        (r"晕影", "暗角"),
        (r"胶片颗粒", "胶片颗粒"),
        (r"色差", "色差"),
        (r"曝光", "曝光"),
        (r"反射", "反射"),
        (r"折射", "折射"),
        (r"镜面(?:高光)?", "高光"),
        (r"法线贴图", "法线贴图"),
        (r"多级纹理", "多级纹理"),
        (r"细节层次", "细节层级"),
        (r"衰减", "衰减"),
        (r"混响", "混响"),
        (r"遮挡", "遮挡"),
        (r"头相关传递函数", "头相关传输函数（HRTF）"),
        (r"空间(?:音频|声音|音效)", "空间音效"),
        (r"采样率", "采样率"),
        (r"音量", "音量"),
        (r"静音", "静音"),
        (r"麦克风", "麦克风"),
        (r"解说员", "解说语音"),
        (r"无线电", "无线电语音"),
        (r"最大值", "最大值"),
        (r"最小值", "最小值"),
        (r"默认值", "默认值"),
        (r"如果非零", "非 0 时"),
        (r"如果为零", "为 0 时"),
        (r"如果(?:该值)?(?:被)?设为 1", "设为 1 时"),
        (r"设为 1 表示", "设为 1 表示"),
        (r"有效值(?:为|是)", "取值范围"),
        (r"允许值(?:为|是)", "允许取值"),
        (r"以秒为单位", "（单位：秒）"),
        (r"以毫秒为单位", "（单位：毫秒）"),
        (r"以分钟为单位", "（单位：分钟）"),
        (r"秒(?:钟)?内", "秒内"),
        (r"毫秒内", "毫秒内"),
    ]
    for pat, rep in fixes:
        t = re.sub(pat, rep, t)
    # 修正重复的「机器人 Bot Bot」
    t = re.sub(r"(机器人 Bot)(\s*Bot)+", r"\1", t)
    t = re.sub(r"当\s*非零\s*时", "非 0 时", t)
    # 离线模型（Argos）常见毛病：术语漏译
    extra = [
        (r"\bbots\b", "机器人 Bot"),
        (r"\bBot\b", "机器人 Bot"),
        (r"拉格多(?:尔)?", "尸体模型"),
        (r"拉格玩偶", "尸体模型"),
        (r"死亡摄像头", "死亡镜头"),
        (r"冻结摄像头", "冻结镜头"),
        (r"摄像机", "镜头"),
        (r"手榴弹", "投掷物"),
        (r"手雷", "投掷物"),
        (r"动词记录", "详细日志"),
        (r"动词(?:级)?日志", "详细日志"),
        (r"时间播放器无法跳过", "玩家被禁止跳过"),
        (r"绘制异形血液", "显示异形血液"),
        (r"镜头的有效射程", "每枪的有效射程"),
        (r"每枪都画一个圈", "每开一枪绘制一个圆"),
        (r"服务器上允许的最大客户端数量", "服务器允许的最大客户端数量"),
        (r"替代的雷达(?:尺度|比例|刻度)", "备用雷达缩放"),
        (r"日光光+", "日光 PVS"),
        (r"太阳光光+", "日光 PVS"),
        (r"天空光+", "天空 PVS"),
        (r"(.)\1{5,}", r"\1\1\1"),          # 压掉长串重复字符（离线模型的循环退化）
    ]
    for pat, rep in extra:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("，,", "，").replace("。。", "。").replace(" .", "。")
    t = re.sub(r"\s+([。，、；：])", r"\1", t)
    return t


def load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def use_cache(path):
    """把缓存路径指向指定文件（并行分片时每个进程写自己的文件，避免互相覆盖）。"""
    global CACHE
    CACHE = Path(path)


def save_cache(cache):
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(CACHE)


def translate_argos(text):
    """离线模型（Argos Translate en→zh）翻译。句子切分用内置 MiniSBD，避免联网下载。"""
    import os
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "false")
    import argostranslate.translate as AT
    out = AT.translate(text[:900], "en", "zh")
    return norm_zh(out)


def translate(text, tries=4, engine="mymemory"):
    """翻译一条；返回中文，失败抛异常。"""
    if engine == "argos":
        return translate_argos(text)
    q = urllib.parse.quote(text[:490])
    url = API.format(q)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CS2ConsoleHub/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            status = d.get("responseStatus")
            if status == 200:
                t = d.get("responseData", {}).get("translatedText", "")
                if t and not t.startswith("MYMEMORY WARNING"):
                    return norm_zh(t)
            if d.get("quotaFinished"):
                raise RuntimeError("QUOTA_FINISHED")
            last = f"status={status} detail={str(d.get('responseDetails'))[:120]}"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
        except RuntimeError:
            raise
        except Exception as e:
            last = str(e)[:120]
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(last or "unknown")


def targets(db, scope):
    """挑出需要翻译的条目，按英文原文去重。"""
    out, seen = [], set()
    for e in db["entries"]:
        if e.get("q") == 2:
            continue
        en = (e.get("en") or "").strip()
        if not en or len(en) < 4:
            continue
        if scope == "core" and not e.get("k"):
            continue
        if scope == "rest" and e.get("k"):
            continue
        key = en.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"en": en, "names": [e["n"]]})
    # 把同名说明合并
    by_en = {}
    for e in db["entries"]:
        by_en.setdefault((e.get("en") or "").strip().lower(), []).append(e["n"])
    for o in out:
        o["names"] = by_en.get(o["en"].lower(), [])[:8]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--priority", default="core", choices=["core", "rest", "all"])
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cache", default="", help="缓存文件路径（并行分片时各自一份）")
    ap.add_argument("--slice", default="", help="分片，形如 2/3 表示取第 2 片（共 3 片）")
    ap.add_argument("--engine", default="mymemory", choices=["mymemory", "argos"],
                    help="翻译引擎：mymemory（在线，质量好但有限额）/ argos（离线，无限量）")
    args = ap.parse_args()
    if args.cache:
        use_cache(args.cache)

    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    cache = load_cache()
    tgt = targets(db, args.priority)
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        tgt = [t for idx, t in enumerate(tgt) if idx % n == i - 1]
    todo = [t for t in tgt if t["en"].lower() not in cache]
    print(f"[i] 范围={args.priority} 分片={args.slice or '-'} 缓存={CACHE.name} "
          f"待翻译条目组={len(tgt)} 已缓存={len(tgt) - len(todo)} 还需请求={len(todo)}")
    if args.stats or args.limit == -1:
        return
    if args.limit:
        todo = todo[:args.limit]

    done = failed = 0
    t0 = time.time()
    for i, item in enumerate(todo, 1):
        try:
            zh = translate(item["en"], engine=args.engine)
            cache[item["en"].lower()] = {
                "zh": zh, "src": args.engine,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            done += 1
        except RuntimeError as e:
            if "QUOTA_FINISHED" in str(e):
                print("[!] 今日配额用尽，已完成的会保留，明天可继续跑（断点续传）")
                break
            failed += 1
            cache.setdefault(item["en"].lower(), {})
            print(f"  [!] 失败 {i}: {str(e)[:80]}  <- {item['en'][:60]}")
        if i % 25 == 0 or i == len(todo):
            save_cache(cache)
            el = time.time() - t0
            eta = (el / i) * (len(todo) - i) if i else 0
            print(f"  {i}/{len(todo)}  成功 {done}  失败 {failed}  用时 {el/60:.1f} 分  预计还需 {eta/60:.1f} 分")
        time.sleep(0.12)
    save_cache(cache)
    print(f"[完成] 本次新增 {done} 条，失败 {failed} 条，缓存总计 {len(cache)} 条")


if __name__ == "__main__":
    main()
