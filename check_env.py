# -*- coding: utf-8 -*-
"""
环境自检：一次性检查「模拟器 / 虚拟声卡 / 语音合成」三件事是否就绪。

    python check_env.py
    python check_env.py --serial 127.0.0.1:16416
"""
import argparse
import asyncio
import os
import tempfile
import time

OK = '[通过]'
NG = '[失败]'
WN = '[注意]'

results = []


def item(name, ok, detail='', fix=''):
    results.append((name, ok, detail, fix))
    tag = OK if ok is True else (WN if ok is None else NG)
    print('%s %s%s' % (tag, name, ('  —  ' + detail) if detail else ''), flush=True)


def check_packages():
    missing = []
    for mod, pkg in [('uiautomator2', 'uiautomator2'), ('sounddevice', 'sounddevice'),
                     ('soundfile', 'soundfile'), ('scipy', 'scipy'),
                     ('numpy', 'numpy'), ('edge_tts', 'edge-tts')]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        item('Python 依赖', False, '缺少：' + ', '.join(missing),
             'pip install -r requirements.txt')
    else:
        item('Python 依赖', True, '全部已安装')


def check_device(serial):
    try:
        import uiautomator2 as u2
    except ImportError:
        item('模拟器连接', False, 'uiautomator2 未安装', 'pip install -r requirements.txt')
        return None

    try:
        d = u2.connect(serial)
    except Exception as e:
        item('模拟器连接', False, '连接 %s 失败：%s' % (serial, e),
             '确认模拟器已开启 ADB 调试，端口与 --serial 一致')
        return None

    try:
        info = d.info
        item('模拟器连接', True, '%s  Android %s' % (
            info.get('productName') or '未知机型', info.get('version', '?')))
    except Exception as e:
        item('模拟器连接', False, '读取设备信息失败：%s' % e)
        return None

    # App 是否安装
    try:
        pkg_info = d.app_info('com.iflytek.elpmobile.student')
        ver = pkg_info.get('versionName') if pkg_info else None
        item('智学网学生端', True, '已安装，版本 %s' % ver if ver else '已安装')
    except Exception:
        item('智学网学生端', False, '未检测到 App',
             '在模拟器里安装并登录智学网学生端')
        return d

    # 当前前台页面
    try:
        cur = d.app_current()
        in_app = cur.get('package') == 'com.iflytek.elpmobile.student'
        item('当前前台', True if in_app else None,
             cur.get('package', '?') + ' / ' + (cur.get('activity') or ''),
             '' if in_app else '正式运行前请切到智学网学生端，并停在某一段的录音页')
    except Exception:
        pass

    # 朗读页关键控件
    try:
        has_record = d(resourceId='com.iflytek.elpmobile.student:id/iv_record').exists
        has_index = d(resourceId='com.iflytek.elpmobile.student:id/text_index').exists
        if has_record and has_index:
            item('朗读页控件', True, '找到录音键与段号')
        else:
            item('朗读页控件', None, '未找到录音键/段号（当前不在朗读页则正常）',
                 '若已在朗读页仍提示失败，多半是 App 版本改了 resource-id')
    except Exception as e:
        item('朗读页控件', None, '读取界面失败：%s' % e)

    return d


def check_audio():
    try:
        import sounddevice as sd
    except ImportError:
        item('虚拟声卡', False, 'sounddevice 未安装', 'pip install -r requirements.txt')
        return None

    hostapis = [h['name'] for h in sd.query_hostapis()]
    found = []
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_output_channels'] > 0 and 'CABLE Input' in dev['name']:
            found.append((i, dev['name'], hostapis[dev['hostapi']],
                          dev['default_samplerate']))
    if not found:
        item('虚拟声卡 CABLE Input', False, '未找到播放设备',
             '安装 VB-CABLE 后重启电脑；确认设备未被禁用')
        return None

    wasapi = [f for f in found if 'wasapi' in f[2].lower()]
    pick = wasapi[0] if wasapi else found[0]
    item('虚拟声卡 CABLE Input', True, '#%d %s (%s, %.0f Hz)' % (
        pick[0], pick[1], pick[2], pick[3]))

    # 试播一声，确认能打开设备
    try:
        import numpy as np
        tone = np.zeros((4800, 1), dtype='float32')
        sd.play(tone, 48000, device=pick[0])
        sd.wait()
        item('音频输出通路', True, '设备可正常打开')
    except Exception as e:
        item('音频输出通路', False, '播放失败：%s' % e, '检查 VB-CABLE 是否被其他程序独占')
    return pick[0]


def check_tts(voice):
    try:
        import edge_tts
    except ImportError:
        item('语音合成', False, 'edge-tts 未安装', 'pip install -r requirements.txt')
        return False

    out = os.path.join(tempfile.gettempdir(), 'zx_tts_check.mp3')
    try:
        async def go():
            await edge_tts.Communicate('环境自检通过', voice).save(out)
        t0 = time.time()
        asyncio.run(asyncio.wait_for(go(), timeout=25))
        size = os.path.getsize(out)
        item('语音合成 edge-tts', True, '%s，%d 字节，%.1f 秒' % (voice, size, time.time() - t0))
        return True
    except Exception as e:
        item('语音合成 edge-tts', False, str(e),
             '需要联网访问微软 TTS；公司/校园网可能被拦，换网络或代理再试')
        return False
    finally:
        if os.path.exists(out):
            try:
                os.remove(out)
            except Exception:
                pass


def check_mic_hint():
    """只能给提示：模拟器麦克风是否指到 CABLE Output 需要人工确认。"""
    item('模拟器麦克风', None,
         '需人工确认：模拟器「设置 → 音频 → 麦克风」应选 CABLE Output (VB-Audio Virtual Cable)',
         '若录音一直是“请正常朗读”或波纹不动，多半是这里没选对')


def main():
    ap = argparse.ArgumentParser(description='智学网朗读脚本环境自检')
    ap.add_argument('--serial', default='127.0.0.1:16416', help='模拟器 adb 地址')
    ap.add_argument('--voice', default='zh-CN-YunjianNeural', help='用于测试的音色')
    args = ap.parse_args()

    print('=== 智学网朗读脚本 环境自检 ===\n', flush=True)
    check_packages()
    check_device(args.serial)
    check_audio()
    check_tts(args.voice)
    check_mic_hint()

    fails = [r for r in results if r[1] is False]
    warns = [r for r in results if r[1] is None]
    print('\n=== 结果：%d 项通过，%d 项失败，%d 项待确认 ===' % (
        len(results) - len(fails) - len(warns), len(fails), len(warns)), flush=True)
    if fails:
        print('\n需要先解决的问题：', flush=True)
        for name, _, _, fix in fails:
            print('  · %s：%s' % (name, fix or '见上文'), flush=True)
        return 1
    if warns:
        print('\n可继续，但请留意上面的待确认项。', flush=True)
    else:
        print('\n环境就绪，可以运行：python auto_read.py --mode one', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
